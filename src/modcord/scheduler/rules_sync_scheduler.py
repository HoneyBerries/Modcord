"""Scheduler for periodic synchronization of server rules across all guilds."""

from __future__ import annotations

import discord

from modcord.configuration.app_configuration import app_config
from modcord.settings.guild_settings_manager import guild_settings_manager
from modcord.datatypes.discord_datatypes import GuildID
from modcord.util.discord import collector
from modcord.scheduler.generic_sync_scheduler import GenericSyncScheduler


async def sync_rules(guild: discord.Guild) -> str:
    """Collect rules from rule-like channels and persist to guild settings."""
    rules_text = await collector.collect_rules(guild)
    guild_settings_manager.update(GuildID(guild.id), rules=rules_text)
    return rules_text


rules_sync_scheduler = GenericSyncScheduler(
    name="RULES_SYNC",
    per_guild_coro=sync_rules,
    get_interval=lambda: app_config.rules_sync_interval,
)