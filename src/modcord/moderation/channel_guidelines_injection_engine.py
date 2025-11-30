"""Engine for collecting and injecting channel-specific guidelines into the moderation context.

This module handles the core logic for:
- Extracting channel-specific guidelines from channel topics
- Persisting collected guidelines to guild settings for moderation use
"""

from __future__ import annotations

import discord

from modcord.configuration.guild_settings import guild_settings_manager
from modcord.datatypes.discord_datatypes import GuildID, ChannelID
from modcord.util.logger import get_logger

logger = get_logger("channel_guidelines_injection_engine")


class ChannelGuidelinesInjectionEngine:
    """
    Engine for collecting and injecting channel-specific guidelines into the moderation context.
    
    This engine extracts channel topics as channel-specific moderation guidelines,
    allowing each channel to have unique moderation rules separate from server-wide rules.
    Guidelines are persisted to guild_settings_manager for quick access.
    
    Methods:
        collect_channel_guidelines: Extract guidelines from a channel's topic.
        sync_channel_guidelines: Fetch and persist latest guidelines for a channel.
        sync_all_channel_guidelines: Sync guidelines for all text channels in a guild.
    """

    def __init__(self) -> None:
        """Initialize the channel guidelines injection engine."""
        logger.info("[CHANNEL GUIDELINES ENGINE] Channel guidelines injection engine initialized")

    async def collect_channel_guidelines(self, channel: discord.TextChannel) -> str:
        """
        Collect channel-specific guidelines from the channel topic.
        
        Extracts the channel's topic text as channel-specific moderation guidelines.
        This allows each channel to have unique moderation rules separate from
        server-wide rules.
        
        Args:
            channel (discord.TextChannel): The channel to extract guidelines from.
        
        Returns:
            str: The channel topic text, or empty string if no topic is set.
        """
        if channel.topic and isinstance(channel.topic, str):
            topic_text = channel.topic.strip()
            if topic_text:
                logger.debug(
                    "[CHANNEL GUIDELINES ENGINE] Collected %d characters of guidelines (channel topic) for channel %s (%s)",
                    len(topic_text),
                    channel.name,
                    channel.id,
                )
                return topic_text

        logger.debug("[CHANNEL GUIDELINES ENGINE] No channel topic found for channel %s (%s)", channel.name, channel.id)
        return ""

    async def sync_channel_guidelines(self, channel: discord.TextChannel) -> str:
        """
        Fetch and persist the latest guidelines for a specific channel.
        
        Extracts guidelines from the channel topic and stores them in the
        guild settings manager. If collection fails, the cached value is
        left untouched and the exception is propagated.
        
        Args:
            channel (discord.TextChannel): The channel to sync guidelines for.
        
        Returns:
            str: The collected guidelines text.
        
        Raises:
            Exception: If guidelines collection fails.
        """
        guild = channel.guild
        if not guild:
            logger.warning("[CHANNEL GUIDELINES ENGINE] Channel %s has no guild", channel.name)
            return ""

        try:
            guidelines_text = await self.collect_channel_guidelines(channel)
        except Exception:
            logger.exception(
                "[CHANNEL GUIDELINES ENGINE] Failed to collect guidelines for channel %s in guild %s",
                channel.name,
                guild.name,
            )
            raise

        guild_settings_manager.set_channel_guidelines(GuildID(guild.id), ChannelID(channel.id), guidelines_text)
        logger.debug(
            "[CHANNEL GUIDELINES ENGINE] Cached %d characters of guidelines for channel %s (%s) in guild %s",
            len(guidelines_text),
            channel.name,
            channel.id,
            guild.name,
        )
        return guidelines_text

    async def sync_all_channel_guidelines(self, guild: discord.Guild) -> None:
        """
        Sync guidelines for all text channels in a guild.
        
        Iterates through all text channels in the guild and syncs their individual
        guidelines. Errors in individual channels are logged but don't stop the process.
        
        Args:
            guild (discord.Guild): The guild to sync channel guidelines for.
        """
        logger.debug("[CHANNEL GUIDELINES ENGINE] Syncing guidelines for all channels in guild %s", guild.name)

        for channel in guild.text_channels:
            try:
                await self.sync_channel_guidelines(channel)
            except Exception as exc:
                logger.warning(
                    "[CHANNEL GUIDELINES ENGINE] Failed to sync guidelines for channel %s in guild %s: %s",
                    channel.name,
                    guild.name,
                    exc,
                )


# Global instance
channel_guidelines_injection_engine = ChannelGuidelinesInjectionEngine()
