"""
Message Processing Service.

Owns the entire pipeline between raw Discord messages and a
ServerModerationBatch ready for the AI engine:

  1. Convert discord.Message  →  ModerationMessage  (including images)
  2. Group messages by channel and fetch per-channel historical context
  3. Deduplicate users across channels and resolve Discord member objects
  4. Bulk-fetch past actions from the database
  5. Build a single ServerModerationBatch with per-channel context
  6. Forward the batch to ModerationPipeline.execute()

Nothing in this service knows about Cogs or queues — it only talks to
infrastructure helpers (history fetcher, database, guild settings, image utils)
and the AI moderation pipeline.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Set, TYPE_CHECKING

import discord

from modcord.configuration.app_configuration import app_config
from modcord.database.database import database
from modcord.datatypes.discord_datatypes import (
    ChannelID,
    DiscordUsername,
    GuildID,
    MessageID,
    UserID,
)
from modcord.datatypes.moderation_datatypes import (
    ChannelContext,
    ServerModerationBatch,
    ModerationMessage,
    ModerationUser,
)
from modcord.history.discord_history_fetcher import DiscordHistoryFetcher
from modcord.moderation.moderation_pipeline import ModerationPipeline
from modcord.settings.guild_settings_manager import guild_settings_manager
from modcord.util import image_utils
from modcord.util.discord import discord_utils
from modcord.util.logger import get_logger

logger = get_logger("message_processing_service")


class MessageProcessingService:
    """
    Converts, enriches, and dispatches batches of raw Discord messages
    through the AI moderation pipeline.

    Messages from ALL channels in a guild are processed together into a
    single ServerModerationBatch, enabling cross-channel pattern detection.

    Parameters
    ----------
    bot:
        The Discord bot instance — needed to resolve channels and guilds.
    moderation_pipeline:
        The AI pipeline that consumes ServerModerationBatch objects.
    history_fetcher:
        Utility that fetches historical channel messages.
    """

    def __init__(
        self,
        bot: discord.Bot,
        moderation_pipeline: ModerationPipeline,
        history_fetcher: DiscordHistoryFetcher,
    ) -> None:
        self._bot = bot
        self._pipeline = moderation_pipeline
        self._history_fetcher = history_fetcher

    # ------------------------------------------------------------------
    # Public API — called by ModerationQueueService
    # ------------------------------------------------------------------

    async def process_batch(self, raw_messages: List[discord.Message]) -> None:
        """
        Full processing pipeline for one guild batch (multi-channel).

        Steps
        -----
        1. Gate on AI-enabled guild setting.
        2. Group raw messages by channel.
        3. Convert each discord.Message to ModerationMessage.
        4. Fetch historical context per channel.
        5. Deduplicate users across channels, enrich each user.
        6. Build channel context with per-channel guidelines.
        7. Build a single ServerModerationBatch.
        8. Forward to ModerationPipeline.execute().
        """
        if not raw_messages:
            return


        # Step 1 — gate on AI-enabled guild setting
        guild = raw_messages[0].guild
        if guild is None:
            return

        guild_id = GuildID.from_guild(guild)
        settings = await guild_settings_manager.get_settings(guild_id)
        if not settings.ai_enabled:
            logger.debug("AI moderation disabled for guild %s — skipping batch", guild_id)
            return


        # Step 2 — group raw messages by channel
        messages_by_channel: Dict[ChannelID, List[discord.Message]] = defaultdict(list)
        for msg in raw_messages:
            if msg.channel is not None:
                ch_id = ChannelID.from_channel(msg.channel)
                messages_by_channel[ch_id].append(msg)


        # Step 3 — convert raw messages per channel
        mod_messages_by_channel: Dict[ChannelID, List[ModerationMessage]] = {}
        for ch_id, ch_msgs in messages_by_channel.items():
            converted: List[ModerationMessage] = []
            
            for raw_msg in ch_msgs:
                mod_msg = await self._convert_message(raw_msg)
                if mod_msg is not None:
                    converted.append(mod_msg)
            if converted:
                mod_messages_by_channel[ch_id] = converted

        if not mod_messages_by_channel:
            return


        # Step 4 — fetch historical context per channel
        all_history_messages: List[ModerationMessage] = []
        for ch_id, ch_mod_msgs in mod_messages_by_channel.items():
            exclude_ids = {m.message_id for m in ch_mod_msgs}
            history = await self._history_fetcher.fetch_history_context(
                channel_id=ch_id,
                exclude_message_ids=exclude_ids,
                history_limit=app_config.history_context_messages,
            )
            all_history_messages.extend(history)

        # Step 5 — deduplicate users across ALL channels
        all_mod_messages: List[ModerationMessage] = []
        for ch_mod_msgs in mod_messages_by_channel.values():
            all_mod_messages.extend(ch_mod_msgs)

        users = await self._group_messages_by_user(all_mod_messages, guild)
        history_users = (
            await self._group_messages_by_user(all_history_messages, guild)
            if all_history_messages
            else []
        )

        if not users:
            logger.debug("No valid users in batch for guild %s", guild_id)
            return

        # Step 6 — build channel context with per-channel guidelines
        guidelines_map = guild_settings_manager.get_cached_guidelines(guild_id)
        channels: Dict[ChannelID, ChannelContext] = {}
        for ch_id, ch_mod_msgs in mod_messages_by_channel.items():
            channel_obj = self._bot.get_channel(int(ch_id))
            channel_name = channel_obj.name if channel_obj is not None else f"Channel {ch_id}" # type: ignore
            
            channel_guidelines = guidelines_map.get(ch_id, "")
            channels[ch_id] = ChannelContext(
                channel_id=ch_id,
                channel_name=channel_name,
                guidelines=channel_guidelines,
                message_count=len(ch_mod_msgs),
            )

        # Step 7 — build the server-wide batch
        batch = ServerModerationBatch(
            guild_id=guild_id,
            channels=channels,
            users=tuple(users),
            history_users=tuple(history_users),
        )

        logger.debug(
            "Forwarding server batch to pipeline — guild=%s channels=%d users=%d history_users=%d",
            guild_id,
            len(channels),
            len(users),
            len(history_users),
        )

        # Step 8 — forward to pipeline
        await self._pipeline.execute(batch)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _convert_message(self, message: discord.Message) -> ModerationMessage | None:
        """Convert a raw discord.Message into a ModerationMessage."""
        if message.guild is None or message.channel is None:
            return None

        images = image_utils.extract_images_for_moderation(message)

        return ModerationMessage(
            message_id=MessageID.from_message(message),
            user_id=UserID.from_user(message.author),
            content=message.clean_content or "",
            timestamp=message.created_at,
            guild_id=GuildID.from_guild(message.guild),
            channel_id=ChannelID.from_channel(message.channel),
            images=tuple(images),
        )

    async def _group_messages_by_user(
        self,
        messages: List[ModerationMessage],
        guild: discord.Guild,
    ) -> List[ModerationUser]:
        """
        Group ModerationMessages by user_id across all channels in the guild,
        resolve each user's Discord member object, and bulk-fetch their past
        moderation actions.

        Preserves the order of first-appearance so the batch is chronological.
        """
        user_msgs: dict[UserID, List[ModerationMessage]] = defaultdict(list)
        first_seen: dict[UserID, int] = {}

        for idx, msg in enumerate(messages):
            uid = msg.user_id
            if uid not in first_seen:
                first_seen[uid] = idx
            user_msgs[uid].append(msg)

        guild_id = GuildID.from_guild(guild)
        lookback = app_config.past_actions_lookback_minutes

        # Bulk DB query — one round-trip for all users
        all_user_ids = list(user_msgs.keys())
        bulk_past_actions = await database.get_bulk_past_actions(guild_id, all_user_ids, lookback)

        users: List[ModerationUser] = []
        for uid, msgs in user_msgs.items():
            member = guild.get_member(int(uid))
            if member is None:
                logger.debug("Member %s not found in guild %s — skipping", uid, guild.id)
                continue

            join_date = (
                member.joined_at
                if member.joined_at is not None
                else datetime.now(timezone.utc)
            )

            users.append(
                ModerationUser(
                    user_id=uid,
                    username=DiscordUsername.from_member(member),
                    join_date=join_date,
                    discord_member=member,
                    discord_guild=guild,
                    roles=tuple(role.name for role in member.roles),
                    messages=tuple(msgs),
                    past_actions=tuple(bulk_past_actions.get(uid, [])),
                )
            )

        users.sort(key=lambda u: first_seen[u.user_id])
        return users
