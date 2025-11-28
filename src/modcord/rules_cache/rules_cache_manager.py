"""Unified manager for discovering, caching, and refreshing both server rules and channel guidelines.

This module replaces the legacy rules_manager.py with a more comprehensive approach that handles:
- Server-wide rules discovery from dedicated rules channels
- Channel-specific guidelines from pinned messages and channel topics
- Automatic periodic refresh for both types
- Integration with guild_settings for persistence
"""

from __future__ import annotations

import asyncio
import re
from typing import List
import discord

from modcord.configuration.guild_settings import guild_settings_manager
from modcord.configuration.app_configuration import app_config
from modcord.datatypes.discord_datatypes import GuildID, ChannelID
from modcord.util.logger import get_logger
from modcord.util.discord_utils import extract_embed_text_from_message

logger = get_logger("rules_cache_manager")


RULE_CHANNEL_PATTERN = re.compile(
    r"(?<!moderationr[_-]?only)(rules?|guidelines?|regulations?|policy|policies|code[-_ ]?of[-_ ]?conduct|server[-_ ]?(rules?|guidelines?)|mod[-_ ]?(rule?|guidelines?)|law|expectations?|standards?)",
    re.IGNORECASE,
)
"""Heuristic regex used to discover channels that likely contain server rules."""


class RulesCacheManager:
    """
    Manager for auto-discovering, caching, and refreshing server rules and channel guidelines.
    
    This manager handles two types of moderation context:
    1. Server Rules: Discovered from channels matching rule-related name patterns
    2. Channel Guidelines: Extracted from individual channel topics
    
    Both types are automatically refreshed on a configurable interval and cached
    in the guild_settings_manager for quick access during moderation.
    
    Methods:
        collect_server_rules: Discover and collect rules from guild channels.
        collect_channel_guidelines: Extract guidelines from channel topics.
        refresh_guild_rules: Fetch and persist latest server rules.
        refresh_channel_guidelines: Fetch and persist channel-specific guidelines.
        refresh_all_guilds: Refresh rules and guidelines for all guilds.
        run_periodic_refresh: Continuously refresh on a fixed interval.
    """

    def __init__(self):
        """Initialize the rules cache manager."""
        self._refresh_task: asyncio.Task | None = None
        self._bot: discord.Bot | None = None
        logger.info("[RULES CACHE MANAGER] Rules cache manager initialized")

    @staticmethod
    

    @staticmethod
    def _is_rules_channel(channel: discord.abc.GuildChannel) -> bool:
        """
        Check if a channel name matches the rules channel pattern.
        
        Uses a regex pattern to identify channels likely to contain server rules
        based on common naming conventions (rules, guidelines, regulations, etc.).
        
        Args:
            channel (discord.abc.GuildChannel): The channel to check.
        
        Returns:
            bool: True if the channel name matches the rules pattern, False otherwise.
        """
        name = channel.name
        if not name:
            return False
        return RULE_CHANNEL_PATTERN.search(name) is not None

    async def _collect_channel_messages(self, channel: discord.TextChannel) -> List[str]:
        """
        Collect all message text and embed content from a single channel.
        
        Fetches up to 100 messages from the channel in chronological order and
        extracts both direct message content and text from embeds. Individual
        channel errors are logged but don't abort the collection process.
        
        Args:
            channel (discord.TextChannel): The channel to collect messages from.
        
        Returns:
            List[str]: List of message text strings (both content and embeds).
        """
        messages = []
        try:
            async for message in channel.history(oldest_first=True):
                if message.content and isinstance(message.content, str) and (text := message.content.strip()):
                    messages.append(text)
                for embed in message.embeds:
                    messages.extend(extract_embed_text_from_message(embed))
                    
        except discord.Forbidden:
            logger.warning("[RULES CACHE MANAGER] No permission to read channel: %s", channel.name)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[RULES CACHE MANAGER] Error fetching messages from channel %s: %s", channel.name, exc)
        return messages

    async def collect_server_rules(self, guild: discord.Guild) -> str:
        """
        Collect server rule text from all channels matching the rule pattern in a guild.
        
        Searches all text channels in the guild for rule-related names and collects
        their message content. Errors in individual channels are logged and skipped.
        
        Args:
            guild (discord.Guild): The guild to collect rules from.
        
        Returns:
            str: Concatenated rules text from all matching channels, or empty string
                if no rules are found.
        """
        all_messages = []
        for channel in guild.text_channels:
            if self._is_rules_channel(channel):
                all_messages.extend(await self._collect_channel_messages(channel))
        
        if not all_messages:
            logger.debug("[RULES CACHE MANAGER] No rule-like content discovered in guild %s", guild.name)
            return ""
        
        logger.debug("[RULES CACHE MANAGER] Collected %d rule messages in guild %s", len(all_messages), guild.name)
        return "\n\n".join(all_messages)

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
        # Simply use the channel topic as the guidelines
        if channel.topic and isinstance(channel.topic, str):
            topic_text = channel.topic.strip()
            if topic_text:
                logger.debug(
                    "Collected %d characters of guidelines (channel topic) for channel %s (%s)",
                    len(topic_text),
                    channel.name,
                    channel.id
                )
                return topic_text

        logger.debug("[RULES CACHE MANAGER] No channel topic found for channel %s (%s)", channel.name, channel.id)
        return ""

    async def refresh_guild_rules(self, guild: discord.Guild) -> str:
        """
        Fetch and persist the latest server rules for a guild.
        
        Collects rules from all rule-related channels and stores them in the
        guild settings manager. If collection fails, the cached value is left
        untouched and the exception is propagated.
        
        Args:
            guild (discord.Guild): The guild to refresh rules for.
        
        Returns:
            str: The collected rules text.
        
        Raises:
            Exception: If rules collection fails.
        """
        try:
            rules_text = await self.collect_server_rules(guild)
        except Exception:
            logger.exception("Failed to collect rules for guild %s", guild.name)
            raise

        guild_settings_manager.set_server_rules(GuildID(guild.id), rules_text)
        logger.debug("[RULES CACHE MANAGER] Cached %d characters of rules for guild %s", len(rules_text), guild.name)
        return rules_text

    async def refresh_channel_guidelines(self, channel: discord.TextChannel) -> str:
        """
        Fetch and persist the latest guidelines for a specific channel.
        
        Extracts guidelines from the channel topic and stores them in the
        guild settings manager. If collection fails, the cached value is
        left untouched and the exception is propagated.
        
        Args:
            channel (discord.TextChannel): The channel to refresh guidelines for.
        
        Returns:
            str: The collected guidelines text.
        
        Raises:
            Exception: If guidelines collection fails.
        """
        guild = channel.guild
        if not guild:
            logger.warning("[RULES CACHE MANAGER] Channel %s has no guild", channel.name)
            return ""

        try:
            guidelines_text = await self.collect_channel_guidelines(channel)
        except Exception:
            logger.exception(
                "Failed to collect guidelines for channel %s in guild %s",
                channel.name,
                guild.name
            )
            raise

        guild_settings_manager.set_channel_guidelines(GuildID(guild.id), ChannelID(channel.id), guidelines_text)
        logger.debug(
            "[RULES CACHE MANAGER] Cached %d characters of guidelines for channel %s (%s) in guild %s",
            len(guidelines_text),
            channel.name,
            channel.id,
            guild.name
        )
        return guidelines_text

    async def refresh_guild_rules_and_guidelines(self, guild: discord.Guild) -> None:
        """
        Refresh both server rules and all channel guidelines for a guild.
        
        This is the main entry point for refreshing all moderation context for a guild.
        Attempts to refresh server rules first, then iterates through all text channels
        to refresh their individual guidelines. Errors are logged but don't stop the process.
        
        Args:
            guild (discord.Guild): The guild to refresh rules and guidelines for.
        """
        logger.debug("[RULES CACHE MANAGER] Refreshing rules and guidelines for guild %s", guild.name)

        # Refresh server rules
        try:
            await self.refresh_guild_rules(guild)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[RULES CACHE MANAGER] Failed to refresh rules for guild %s: %s", guild.name, exc)

        # Refresh channel guidelines for all text channels
        for channel in guild.text_channels:
            try:
                await self.refresh_channel_guidelines(channel)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "[RULES CACHE MANAGER] Failed to refresh guidelines for channel %s in guild %s: %s",
                    channel.name,
                    guild.name,
                    exc
                )

    async def refresh_all_guilds(self, bot: discord.Bot) -> None:
        """
        Refresh cached rules and guidelines for all guilds the bot is connected to.
        
        Iterates through all guilds and refreshes both server rules and channel
        guidelines. Individual guild errors are logged but don't stop the process.
        
        Args:
            bot (discord.Bot): The Discord bot instance providing guild access.
        """
        logger.debug("[RULES CACHE MANAGER] Refreshing rules/guidelines cache for %d guilds", len(bot.guilds))
        for guild in bot.guilds:
            try:
                await self.refresh_guild_rules_and_guidelines(guild)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("[RULES CACHE MANAGER] Failed to refresh guild %s: %s", guild.name, exc)

    async def run_periodic_refresh(
        self,
        bot: discord.Bot,
        *,
        interval_seconds: float = 600.0,
    ) -> None:
        """
        Continuously refresh rules and guidelines cache on a fixed interval.
        
        Runs an infinite loop that refreshes all guilds' rules and guidelines,
        then sleeps for the specified interval before refreshing again.
        
        Args:
            bot (discord.Bot): Discord client instance whose guilds require periodic refresh.
            interval_seconds (float): Delay between successive refresh runs. Defaults to 600.0 (10 minutes).
        
        Raises:
            asyncio.CancelledError: Propagated when the task is cancelled for shutdown.
        """
        self._bot = bot
        logger.info(
            "[RULES CACHE MANAGER] Starting periodic rules/guidelines refresh (interval=%.1fs) for %d guilds",
            interval_seconds,
            len(bot.guilds),
        )
        try:
            while True:
                try:
                    await self.refresh_all_guilds(bot)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error("[RULES CACHE MANAGER] Unexpected error during rules/guidelines refresh: %s", exc)
                await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            logger.info("[RULES CACHE MANAGER] Periodic rules/guidelines refresh cancelled")
            raise

    async def refresh_if_rules_channel(self, channel: discord.abc.GuildChannel) -> None:
        """
        Refresh guild rules if the specified channel matches the rules channel pattern.
        
        Used to automatically refresh rules when messages are posted in rules channels,
        ensuring the cache stays up-to-date with manual rule updates.
        
        Args:
            channel (discord.abc.GuildChannel): The channel to check and potentially trigger refresh for.
        """
        if not isinstance(channel, discord.TextChannel) or not self._is_rules_channel(channel):
            return

        guild = channel.guild
        if not guild:
            return

        try:
            await self.refresh_guild_rules(guild)
            logger.debug("[RULES CACHE MANAGER] Rules refreshed from channel: %s", channel.name)
        except Exception as exc:
            logger.error("[RULES CACHE MANAGER] Failed to refresh rules from channel %s: %s", channel.name, exc)

    async def start_periodic_task(self, bot: discord.Bot, interval_seconds: float | None = None) -> None:
        """
        Start the periodic rules and guidelines refresh background task.
        
        Creates and runs the periodic refresh task if one isn't already running.
        If interval_seconds is not provided, reads the interval from app_config.
        
        Args:
            bot (discord.Bot): Discord client instance to use for refreshing.
            interval_seconds (float | None): Refresh interval in seconds. If None,
                reads from app_config rules_cache_refresh.interval_seconds.
        """
        if interval_seconds is None:
            interval_seconds = app_config.rules_cache_refresh_interval

        if self._refresh_task and not self._refresh_task.done():
            logger.warning("[RULES CACHE MANAGER] Periodic refresh task already running")
            return

        self._refresh_task = asyncio.create_task(
            self.run_periodic_refresh(bot, interval_seconds=interval_seconds)
        )
        logger.info("[RULES CACHE MANAGER] Started periodic rules/guidelines refresh task")

    async def stop_periodic_task(self) -> None:
        """
        Stop the periodic refresh task if it's currently running.
        
        Cancels the background refresh task and waits for it to complete cleanup.
        Safe to call even if no task is running.
        """
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
            logger.info("[RULES CACHE MANAGER] Stopped periodic rules/guidelines refresh task")

    async def shutdown(self) -> None:
        """
        Cleanly shutdown the rules cache manager.
        
        Stops the periodic refresh task if running and cleans up resources.
        This method should be called during bot shutdown to ensure proper cleanup.
        """
        await self.stop_periodic_task()
        self._bot = None
        self._refresh_task = None
        logger.info("[RULES CACHE MANAGER] Rules cache manager shutdown complete")


# Global instance
rules_cache_manager = RulesCacheManager()