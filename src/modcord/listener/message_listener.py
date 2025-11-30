"""Message listener Cog for Modcord.

This cog handles all message-related Discord events (on_message, on_message_edit)
and processes messages through the AI moderation pipeline.
"""

import asyncio
from datetime import datetime, timezone
from typing import List

import discord
from discord.ext import commands

from modcord.configuration.app_configuration import app_config
from modcord.configuration.guild_settings import guild_settings_manager
from modcord.database.database import get_db
from modcord.datatypes.action_datatypes import ActionData
from modcord.datatypes.discord_datatypes import (
    ChannelID,
    DiscordUsername,
    GuildID,
    MessageID,
    UserID,
)
from modcord.datatypes.moderation_datatypes import (
    ModerationChannelBatch,
    ModerationMessage,
    ModerationUser,
)
from modcord.history.discord_history_fetcher import DiscordHistoryFetcher
from modcord.moderation.moderation_helper import ModerationEngine
from modcord.moderation.rules_injection_engine import rules_injection_engine
from modcord.util import discord_utils
from modcord.util.image_utils import download_images_for_moderation
from modcord.util.logger import get_logger

logger = get_logger("message_listener_cog")


class MessageListenerCog(commands.Cog):
    """Cog responsible for handling message creation and editing events."""

    def __init__(self, discord_bot_instance):
        """
        Initialize the message listener cog.

        Parameters
        ----------
        discord_bot_instance:
            The Discord bot instance to attach this cog to.
        """
        self.bot = discord_bot_instance
        self.discord_bot_instance = discord_bot_instance
        self._moderation_engine = ModerationEngine(discord_bot_instance)
        self._history_fetcher = DiscordHistoryFetcher(discord_bot_instance)
        self._pending_messages: dict[ChannelID, List[ModerationMessage]] = {}
        self._batch_timer: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        logger.info("[MESSAGE LISTENER] Message listener cog loaded")

    @commands.Cog.listener(name='on_message')
    async def on_message(self, message: discord.Message):
        """
        Handle new messages.

        This handler:
        1. Filters out DMs, other bots, and empty messages using centralized logic
        2. Refreshes rules cache if posted in a rules channel
        3. Queues messages for AI moderation processing
        """
        # Use centralized filtering logic
        if not discord_utils.should_process_message(message):
            return

        logger.debug(f"Received message from {message.author}: {message.clean_content[:80] if message.clean_content else '[no text]'}")

        # Sync rules cache if this was posted in a rules channel
        if isinstance(message.channel, discord.TextChannel):
            await rules_injection_engine.sync_if_rules_channel(message.channel)

        # Queue message for moderation processing
        await self._queue_message_for_moderation(message)

    @commands.Cog.listener(name='on_message_edit')
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        """
        Handle message edits by refreshing rules cache if needed.
        """
        # Use centralized filtering logic
        if not discord_utils.should_process_message(after):
            return

        # Sync rules cache if this edit occurred in a rules channel
        if isinstance(after.channel, discord.abc.GuildChannel):
            await rules_injection_engine.sync_if_rules_channel(after.channel)

    async def _queue_message_for_moderation(self, message: discord.Message) -> None:
        """
        Queue a message for batched moderation processing.
        
        Messages are batched per-channel and processed after a configurable delay.
        """
        # Check if AI moderation is enabled for this guild
        if not message.guild:
            return
        
        guild_id = GuildID.from_guild(message.guild)
        if not guild_settings_manager.is_ai_enabled(guild_id):
            logger.debug(f"AI moderation disabled for guild {guild_id}, skipping message")
            return

        # Convert Discord message to ModerationMessage (async for image download)
        mod_message = await self._convert_to_moderation_message(message)
        if not mod_message:
            return

        channel_id = ChannelID.from_channel(message.channel)
        
        async with self._lock:
            if channel_id not in self._pending_messages:
                self._pending_messages[channel_id] = []
            self._pending_messages[channel_id].append(mod_message)
            
            logger.debug(
                f"Queued message {mod_message.message_id} for channel {channel_id} "
                f"(batch size: {len(self._pending_messages[channel_id])})"
            )
            
            # Start the batch timer if not already running
            self._ensure_batch_timer_running()

    async def _convert_to_moderation_message(self, message: discord.Message) -> ModerationMessage | None:
        """
        Convert a Discord message to a ModerationMessage.
        
        Downloads any image attachments and includes them in the ModerationMessage.
        """
        if not message.guild:
            return None
        
        # Download images from attachments
        images = await download_images_for_moderation(message)
        
        return ModerationMessage(
            message_id=MessageID.from_message(message),
            user_id=UserID.from_user(message.author),
            content=message.clean_content or "",
            timestamp=message.created_at,
            guild_id=GuildID.from_guild(message.guild),
            channel_id=ChannelID.from_channel(message.channel),
            images=images,
        )

    def _ensure_batch_timer_running(self) -> None:
        """Start the batch timer if not already running."""
        if self._batch_timer is None or self._batch_timer.done():
            self._batch_timer = asyncio.create_task(self._batch_timer_task())
            logger.debug("Started batch timer")

    async def _batch_timer_task(self) -> None:
        """Wait for the batch interval, then process all pending messages."""
        interval = app_config.moderation_batch_seconds
        logger.debug(f"Batch timer sleeping for {interval} seconds")
        await asyncio.sleep(interval)

        async with self._lock:
            pending = {cid: list(msgs) for cid, msgs in self._pending_messages.items() if msgs}
            self._pending_messages.clear()

        if not pending:
            logger.debug("Batch timer fired but no pending messages")
            self._batch_timer = None
            return

        # Assemble and process batches
        try:
            batches = await self._assemble_batches(pending)
            if batches:
                await self._moderation_engine.process_batches(batches)
        except Exception:
            logger.exception("Exception while processing moderation batches")
        
        self._batch_timer = None

    async def _assemble_batches(
        self, pending: dict[ChannelID, List[ModerationMessage]]
    ) -> List[ModerationChannelBatch]:
        """
        Assemble ModerationChannelBatch objects from pending messages.
        """
        batches: List[ModerationChannelBatch] = []

        for channel_id, messages in pending.items():
            channel = self.bot.get_channel(channel_id.to_int())
            if not isinstance(channel, discord.abc.GuildChannel):
                logger.warning(f"Channel {channel_id} not found or not a guild channel")
                continue

            # Group messages by user and enrich with Discord context
            users = await self._group_messages_by_user(messages, channel)
            if not users:
                continue

            # Fetch historical context
            exclude_ids = {m.message_id for m in messages}
            history_messages = await self._history_fetcher.fetch_history_context(channel_id, exclude_ids)
            history_users = await self._group_messages_by_user(history_messages, channel) if history_messages else []

            logger.debug(
                f"Prepared batch for channel {channel_id}: {len(users)} users, {len(history_users)} history users"
            )

            batches.append(
                ModerationChannelBatch(
                    channel_id=channel_id,
                    channel_name=getattr(channel, "name", str(channel_id)),
                    users=users,
                    history_users=history_users,
                )
            )

        return batches

    async def _group_messages_by_user(
        self, messages: List[ModerationMessage], channel: discord.abc.GuildChannel
    ) -> List[ModerationUser]:
        """
        Group messages by user and enrich with Discord context.
        """
        from collections import defaultdict

        user_msgs: dict[UserID, List[ModerationMessage]] = defaultdict(list)
        first_seen: dict[UserID, int] = {}

        for idx, msg in enumerate(messages):
            uid = msg.user_id
            if uid not in first_seen:
                first_seen[uid] = idx
            user_msgs[uid].append(msg)

        guild = channel.guild
        if guild is None:
            logger.warning(f"Guild not found for channel {channel.id}")
            return []

        guild_id = GuildID.from_guild(guild)
        lookback = app_config.ai_settings.past_actions_lookback_minutes

        users: List[ModerationUser] = []
        for uid, msgs in user_msgs.items():
            member = guild.get_member(uid.to_int())
            if member is None:
                logger.debug(f"Member {uid} not found in guild {guild.id}, skipping")
                continue
            if member.joined_at is None:
                logger.debug(f"Join date missing for member {uid}, using now")
                join_date = datetime.now(timezone.utc)
            else:
                join_date = member.joined_at

            past_actions: List[ActionData] = await get_db().get_past_actions(guild_id, uid, lookback)

            users.append(
                ModerationUser(
                    user_id=uid,
                    username=DiscordUsername.from_user(member),
                    join_date=join_date,
                    discord_member=member,
                    discord_guild=guild,
                    roles=[role.name for role in member.roles],
                    messages=list(msgs),
                    past_actions=past_actions,
                )
            )

        users.sort(key=lambda u: first_seen[u.user_id])
        return users


def setup(discord_bot_instance):
    """Register the MessageListenerCog with the bot."""
    discord_bot_instance.add_cog(MessageListenerCog(discord_bot_instance))
