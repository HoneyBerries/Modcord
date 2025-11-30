"""Engine for discovering and injecting server rules into the moderation context.

This module handles the core logic for:
- Identifying channels that likely contain server rules based on naming conventions
- Collecting message content and embeds from rule channels
- Persisting collected rules to guild settings for moderation use
"""

from __future__ import annotations

import asyncio
import re
from typing import List

import discord

from modcord.configuration.guild_settings import guild_settings_manager
from modcord.datatypes.discord_datatypes import GuildID
from modcord.util.logger import get_logger
from modcord.util.discord_utils import extract_embed_text_from_message

logger = get_logger("rules_injection_engine")


RULE_CHANNEL_PATTERN = re.compile(
    r"^(?:(?!moderation[_-]?only).)*(rules?|guidelines?|regulations?|policy|policies|code[-_ ]?of[-_ ]?conduct|server[-_ ]?(rules?|guidelines?)|mod[-_ ]?(rules?|guidelines?)|law|expectations?|standards?)",
    re.IGNORECASE,
)
"""Heuristic regex used to discover channels that likely contain server rules."""


class RulesInjectionEngine:
    """
    Engine for discovering, collecting, and injecting server rules into the moderation context.
    
    This engine identifies channels containing server rules based on common naming
    conventions and extracts their content for use during AI moderation. Rules are
    persisted to guild_settings_manager for quick access.
    
    Methods:
        is_rules_channel: Check if a channel matches the rules naming pattern.
        collect_channel_messages: Extract all text and embed content from a channel.
        collect_server_rules: Gather rules from all matching channels in a guild.
        sync_guild_rules: Fetch and persist latest server rules for a guild.
    """

    def __init__(self) -> None:
        """Initialize the rules injection engine."""
        logger.info("[RULES INJECTION ENGINE] Rules injection engine initialized")

    @staticmethod
    def is_rules_channel(channel: discord.abc.GuildChannel) -> bool:
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
        
        Fetches messages from the channel in chronological order and extracts
        both direct message content and text from embeds. Individual channel
        errors are logged but don't abort the collection process.
        
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
            logger.warning("[RULES INJECTION ENGINE] No permission to read channel: %s", channel.name)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[RULES INJECTION ENGINE] Error fetching messages from channel %s: %s", channel.name, exc)
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
            if self.is_rules_channel(channel):
                all_messages.extend(await self._collect_channel_messages(channel))

        if not all_messages:
            logger.debug("[RULES INJECTION ENGINE] No rule-like content discovered in guild %s", guild.name)
            return ""

        logger.debug("[RULES INJECTION ENGINE] Collected %d rule messages in guild %s", len(all_messages), guild.name)
        return "\n\n".join(all_messages)

    async def sync_guild_rules(self, guild: discord.Guild) -> str:
        """
        Fetch and persist the latest server rules for a guild.
        
        Collects rules from all rule-related channels and stores them in the
        guild settings manager. If collection fails, the cached value is left
        untouched and the exception is propagated.
        
        Args:
            guild (discord.Guild): The guild to sync rules for.
        
        Returns:
            str: The collected rules text.
        
        Raises:
            Exception: If rules collection fails.
        """
        try:
            rules_text = await self.collect_server_rules(guild)
        except Exception:
            logger.exception("[RULES INJECTION ENGINE] Failed to collect rules for guild %s", guild.name)
            raise

        guild_settings_manager.set_server_rules(GuildID(guild.id), rules_text)
        logger.debug("[RULES INJECTION ENGINE] Cached %d characters of rules for guild %s", len(rules_text), guild.name)
        return rules_text

    async def sync_if_rules_channel(self, channel: discord.abc.GuildChannel) -> None:
        """
        Sync guild rules if the specified channel matches the rules channel pattern.
        
        Used to automatically sync rules when messages are posted in rules channels,
        ensuring the cache stays up-to-date with manual rule updates.
        
        Args:
            channel (discord.abc.GuildChannel): The channel to check and potentially trigger sync for.
        """
        if not isinstance(channel, discord.TextChannel) or not self.is_rules_channel(channel):
            return

        guild = channel.guild
        if not guild:
            return

        try:
            await self.sync_guild_rules(guild)
            logger.debug("[RULES INJECTION ENGINE] Rules synced from channel: %s", channel.name)
        except Exception as exc:
            logger.error("[RULES INJECTION ENGINE] Failed to sync rules from channel %s: %s", channel.name, exc)


# Global instance
rules_injection_engine = RulesInjectionEngine()
