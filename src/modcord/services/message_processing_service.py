from collections import defaultdict
from datetime import datetime, timezone

import discord

from modcord.datatypes.discord_datatypes import GuildID, UserID, DiscordUsername, MessageID, ChannelID
from modcord.datatypes.moderation_datatypes import (
    ModerationMessage, ModerationUserChannel, ModerationUser,
    ChannelContext, ServerModerationBatch)
from modcord.util.discord.history_fetcher import fetch_history_context
from modcord.moderation.moderation_pipeline import ModerationPipeline
from modcord.settings.guild_settings_manager import guild_settings_manager
from modcord.util import image_utils
from modcord.util.logger import get_logger

logger = get_logger("message_processing_service")

class MessageProcessingService:
    """Processes Discord messages into ServerModerationBatch for AI moderation."""

    def __init__(self, bot: discord.Bot, moderation_pipeline: ModerationPipeline):
        self.bot = bot
        self.pipeline = moderation_pipeline

    async def process_batch(self, raw_messages):
        if not raw_messages:
            return

        guild = raw_messages[0].guild
        if not guild:
            return

        settings = await guild_settings_manager.get_settings(guild.id)
        if not settings.ai_enabled:
            logger.debug("AI moderation disabled for guild %s", guild.id)
            return

        # Group messages by channel (using integer IDs from Discord API)
        messages_by_channel_int = defaultdict(list)
        for msg in raw_messages:
            if msg.channel:
                messages_by_channel_int[msg.channel.id].append(msg)

        # Convert messages to ModerationMessage objects
        mod_messages_by_channel = {}
        for ch_id_int, msgs in messages_by_channel_int.items():
            converted = [await self._convert_message(m) for m in msgs]
            converted = [m for m in converted if m]
            if converted:
                # Use integer keys for now, will wrap in ChannelID later
                mod_messages_by_channel[ch_id_int] = converted

        if not mod_messages_by_channel:
            return

        # Fetch history per channel
        history_by_channel = {}
        for ch_id_int, msgs in mod_messages_by_channel.items():
            exclude_ids = {m.message_id for m in msgs}
            history = await fetch_history_context(self.bot, ch_id_int, exclude_ids, history_limit=96)
            if history:
                history_by_channel[ch_id_int] = history

        # Build channel contexts with ChannelID keys
        guidelines_map = await guild_settings_manager.get_guidelines(GuildID(guild.id))
        channels = {}
        for ch_id_int, msgs in mod_messages_by_channel.items():
            ch_obj = self.bot.get_channel(ch_id_int)
            channels[ChannelID(ch_id_int)] = ChannelContext(
                channel_id=ChannelID(ch_id_int),
                channel_name=ch_obj.name if ch_obj else f"Channel {ch_id_int}",
                guidelines=guidelines_map.get(ChannelID(ch_id_int), ""),
                message_count=len(msgs)
            )

        # Build per-user structures
        users = await self._group_by_user(mod_messages_by_channel, channels, guild)
        history_users = await self._group_by_user(history_by_channel, channels, guild) if history_by_channel else ()

        if not users:
            logger.debug("No users found in batch for guild %s", guild.id)
            return

        batch = ServerModerationBatch(
            guild_id=GuildID(guild.id),
            channels=channels,
            users=users,
            history_users=history_users
        )

        logger.debug(
            "Forwarding batch: guild=%s channels=%d users=%d history_users=%d",
            guild.id, len(channels), len(users), len(history_users)
        )

        await self.pipeline.execute(batch)

    async def _convert_message(self, message):
        if not message.guild or not message.channel:
            return None
        images = image_utils.extract_images_for_moderation(message)
        return ModerationMessage(
            message_id=MessageID(message.id),
            user_id=UserID(message.author.id),
            content=message.clean_content or "",
            timestamp=message.created_at,
            guild_id=GuildID(message.guild.id),
            channel_id=ChannelID(message.channel.id),
            images=tuple(images)
        )

    async def _group_by_user(self, messages_by_channel, channel_contexts, guild):
        user_channels_map = defaultdict(list)
        first_seen = {}

        idx = 0
        for ch_id, msgs in messages_by_channel.items():
            for m in msgs:
                if m.user_id not in first_seen:
                    first_seen[m.user_id] = idx
                user_channels_map[m.user_id].append((ch_id, m))
                idx += 1

        users= []
        for user_id, ch_msgs in user_channels_map.items():
            member = guild.get_member(int(user_id))
            if not member:
                continue

            join_date = member.joined_at or datetime.now(timezone.utc)
            # group messages per channel
            channels_dict = defaultdict(tuple)
            for ch_id, msg in ch_msgs:
                channels_dict[ch_id] = channels_dict[ch_id] + (msg,)

            user_channels = tuple(
                ModerationUserChannel(
                    channel_id=ChannelID(ch_id),
                    channel_name=channel_contexts.get(ChannelID(ch_id), f"Channel {ch_id}").channel_name
                    if ChannelID(ch_id) in channel_contexts else f"Channel {ch_id}",
                    messages=msgs  # if msgs is already a tuple, no cast needed
                )
                for ch_id, msgs in channels_dict.items()
            )

            users.append(
                ModerationUser(
                    user_id=user_id,  # Already a UserID object
                    username=DiscordUsername.from_member(member),
                    join_date=join_date,
                    discord_member=member,
                    discord_guild=guild,
                    roles=tuple([role.name for role in member.roles]),
                    channels=user_channels,
                )
            )

        # maintain chronological order
        users.sort(key=lambda u: first_seen[u.user_id])
        return tuple(users)