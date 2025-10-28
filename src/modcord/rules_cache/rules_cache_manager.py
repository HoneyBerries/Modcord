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
from typing import Dict, List

import discord

from modcord.configuration.guild_settings import guild_settings_manager
from modcord.configuration.app_configuration import app_config
from modcord.util.logger import get_logger

logger = get_logger("rules_cache_manager")


RULE_CHANNEL_PATTERN = re.compile(
    r"(guidelines|regulations|policy|policies|server[-_]?rules|rules)",
    re.IGNORECASE,
)
"""Heuristic regex used to discover channels that likely contain server rules."""


class RulesCacheManager:
    """Manager for auto-discovering and caching server rules and channel guidelines."""

    def __init__(self):
        """Initialize the rules cache manager."""
        self._refresh_task: asyncio.Task | None = None
        self._bot: discord.Bot | None = None
        logger.info("Rules cache manager initialized")

    @staticmethod
    def _extract_embed_text(embed: discord.Embed) -> List[str]:
        """Extract text from embed description and fields."""
        texts = []
        if embed.description and isinstance(embed.description, str):
            texts.append(embed.description.strip())
        texts.extend(
            f"{field.name}: {field.value}".strip() if field.name else field.value.strip()
            for field in embed.fields
            if isinstance(field.value, str) and field.value.strip()
        )
        return texts

    @staticmethod
    def _is_rules_channel(channel: discord.abc.GuildChannel) -> bool:
        """Check if channel name matches rules pattern."""
        name = channel.name
        if not name:
            return False
        return RULE_CHANNEL_PATTERN.search(name) is not None

    async def _collect_channel_messages(self, channel: discord.TextChannel) -> List[str]:
        """Collect message and embed text from a single channel.
        
        Logs and skips errors from individual channels so one issue doesn't
        abort the entire collection.
        """
        messages = []
        try:
            async for message in channel.history(oldest_first=True, limit=100):
                if message.content and isinstance(message.content, str) and (text := message.content.strip()):
                    messages.append(text)
                for embed in message.embeds:
                    messages.extend(self._extract_embed_text(embed))
        except discord.Forbidden:
            logger.warning("No permission to read channel: %s", channel.name)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Error fetching messages from channel %s: %s", channel.name, exc)
        return messages

    async def collect_server_rules(self, guild: discord.Guild) -> str:
        """Collect rule text from channels in guild matching RULE_CHANNEL_PATTERN.

        Returns concatenated rules text, or empty string if none found.
        Errors in individual channels are logged and skipped.
        """
        all_messages = []
        for channel in guild.text_channels:
            if self._is_rules_channel(channel):
                all_messages.extend(await self._collect_channel_messages(channel))
        
        if not all_messages:
            logger.debug("No rule-like content discovered in guild %s", guild.name)
            return ""
        
        logger.debug("Collected %d rule messages in guild %s", len(all_messages), guild.name)
        return "\n\n".join(all_messages)

    async def collect_channel_guidelines(self, channel: discord.TextChannel) -> str:
        """Collect channel-specific guidelines from the channel topic.

        Returns the channel topic text, or empty string if none found.
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

        logger.debug("No channel topic found for channel %s (%s)", channel.name, channel.id)
        return ""

    async def refresh_guild_rules(self, guild: discord.Guild) -> str:
        """Fetch and persist latest server rules for guild.

        Returns collected rules text. If collection fails, cached value
        is left untouched and exception is propagated.
        """
        try:
            rules_text = await self.collect_server_rules(guild)
        except Exception:
            logger.exception("Failed to collect rules for guild %s", guild.name)
            raise

        guild_settings_manager.set_server_rules(guild.id, rules_text)
        logger.debug("Cached %d characters of rules for guild %s", len(rules_text), guild.name)
        return rules_text

    async def refresh_channel_guidelines(self, channel: discord.TextChannel) -> str:
        """Fetch and persist latest guidelines for a specific channel.

        Returns collected guidelines text. If collection fails, cached value
        is left untouched and exception is propagated.
        """
        guild = channel.guild
        if not guild:
            logger.warning("Channel %s has no guild", channel.name)
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

        guild_settings_manager.set_channel_guidelines(guild.id, channel.id, guidelines_text)
        logger.debug(
            "Cached %d characters of guidelines for channel %s (%s) in guild %s",
            len(guidelines_text),
            channel.name,
            channel.id,
            guild.name
        )
        return guidelines_text

    async def refresh_guild_rules_and_guidelines(self, guild: discord.Guild) -> None:
        """Refresh both server rules and all channel guidelines for a guild.

        This is the main entry point for refreshing all rules/guidelines for a guild.
        """
        logger.debug("Refreshing rules and guidelines for guild %s", guild.name)

        # Refresh server rules
        try:
            await self.refresh_guild_rules(guild)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Failed to refresh rules for guild %s: %s", guild.name, exc)

        # Refresh channel guidelines for all text channels
        for channel in guild.text_channels:
            try:
                await self.refresh_channel_guidelines(channel)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "Failed to refresh guidelines for channel %s in guild %s: %s",
                    channel.name,
                    guild.name,
                    exc
                )

    async def refresh_all_guilds(self, bot: discord.Bot) -> None:
        """Refresh cached rules and guidelines for all guilds the bot is in."""
        logger.debug("Refreshing rules/guidelines cache for %d guilds", len(bot.guilds))
        for guild in bot.guilds:
            try:
                await self.refresh_guild_rules_and_guidelines(guild)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Failed to refresh guild %s: %s", guild.name, exc)

    async def run_periodic_refresh(
        self,
        bot: discord.Bot,
        *,
        interval_seconds: float = 600.0,
    ) -> None:
        """Continuously refresh rules/guidelines cache on a fixed interval.

        Parameters
        ----------
        bot:
            Discord client instance whose guilds require periodic refresh.
        interval_seconds:
            Delay between successive refresh runs, in seconds.

        Raises
        ------
        asyncio.CancelledError
            Propagated when the enclosing task is cancelled.
        """
        self._bot = bot
        logger.info(
            "Starting periodic rules/guidelines refresh (interval=%.1fs) for %d guilds",
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
                    logger.error("Unexpected error during rules/guidelines refresh: %s", exc)
                await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            logger.info("Periodic rules/guidelines refresh cancelled")
            raise

    async def refresh_if_rules_channel(self, channel: discord.abc.GuildChannel) -> None:
        """Refresh guild rules if channel matches the rules channel pattern."""
        if not isinstance(channel, discord.TextChannel) or not self._is_rules_channel(channel):
            return

        guild = channel.guild
        if not guild:
            return

        try:
            await self.refresh_guild_rules(guild)
            logger.debug("Rules refreshed from channel: %s", channel.name)
        except Exception as exc:
            logger.error("Failed to refresh rules from channel %s: %s", channel.name, exc)

    async def start_periodic_task(self, bot: discord.Bot, interval_seconds: float | None = None) -> None:
        """Start the periodic rules/guidelines refresh background task.

        Parameters
        ----------
        bot:
            Discord client instance
        interval_seconds:
            Refresh interval in seconds. If None, reads from app_config.
        """
        if interval_seconds is None:
            interval_seconds = float(app_config.get("rules_cache_refresh", {}).get("interval_seconds", 600.0))

        if self._refresh_task and not self._refresh_task.done():
            logger.warning("Periodic refresh task already running")
            return

        self._refresh_task = asyncio.create_task(
            self.run_periodic_refresh(bot, interval_seconds=interval_seconds)
        )
        logger.info("Started periodic rules/guidelines refresh task")

    async def stop_periodic_task(self) -> None:
        """Stop the periodic refresh task if running."""
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
            logger.info("Stopped periodic rules/guidelines refresh task")


# Global instance
rules_cache_manager = RulesCacheManager()