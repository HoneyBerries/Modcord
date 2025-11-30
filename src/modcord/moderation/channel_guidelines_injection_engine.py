"""Engine for collecting and injecting channel-specific guidelines."""

from __future__ import annotations

import discord

from modcord.settings.guild_settings_manager import guild_settings_manager
from modcord.datatypes.discord_datatypes import GuildID, ChannelID
from modcord.util.discord import collector
from modcord.util.logger import get_logger

logger = get_logger("guidelines_sync")


class ChannelGuidelinesCollection:
    """Engine for extracting channel topics as moderation guidelines."""

    async def sync_channel_guidelines(self, channel: discord.TextChannel) -> str:
        """Extract channel topic and persist as guidelines in guild settings."""
        guild = channel.guild
        if not guild:
            return ""
        text = collector.collect_channel_topic(channel)
        settings = guild_settings_manager.get(GuildID(guild.id))
        settings.channel_guidelines[ChannelID(channel.id)] = text
        guild_settings_manager.save(GuildID(guild.id))
        return text


    async def sync_all_channel_guidelines(self, guild: discord.Guild) -> None:
        """Sync guidelines for all text channels in a guild."""
        for ch in guild.text_channels:
            await self.sync_channel_guidelines(ch)
        logger.debug("Synced guidelines for %d channels in guild %s", len(guild.text_channels), guild.name)


channel_guidelines_collection = ChannelGuidelinesCollection()