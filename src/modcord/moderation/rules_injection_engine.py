"""Engine for discovering and injecting server rules into the moderation context."""

from __future__ import annotations

import discord

from modcord.configuration.guild_settings import guild_settings_manager
from modcord.datatypes.discord_datatypes import GuildID
from modcord.util import collector
from modcord.util.logger import get_logger

logger = get_logger("rules_engine")


class RulesInjectionEngine:
    """Engine for collecting server rules and persisting them to guild settings."""

    async def sync_guild_rules(self, guild: discord.Guild) -> str:
        """Collect rules from rule-like channels and persist to guild settings."""
        rules_text = await collector.collect_rules(guild)
        guild_settings_manager.set_server_rules(GuildID(guild.id), rules_text)
        logger.debug("Cached %d chars of rules for guild %s", len(rules_text), guild.name)
        return rules_text

    async def sync_if_rules_channel(self, channel: discord.abc.GuildChannel) -> None:
        """Sync guild rules if the channel matches the rules naming pattern."""
        if isinstance(channel, discord.TextChannel) and collector.is_rules_channel(channel) and channel.guild:
            await self.sync_guild_rules(channel.guild)


rules_injection_engine = RulesInjectionEngine()