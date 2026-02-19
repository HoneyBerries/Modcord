"""Scheduler for periodic synchronization of channel guidelines across all guilds."""

from __future__ import annotations

import discord

from modcord.configuration.app_configuration import app_config
from modcord.datatypes.discord_datatypes import GuildID, ChannelID
from modcord.scheduler.generic_sync_scheduler import GenericSyncScheduler
from modcord.settings.guild_settings_manager import guild_settings_manager
from modcord.util.discord import collector


async def sync_all_channel_guidelines(guild: discord.Guild) -> None:
    """Sync guidelines for all text channels in a guild."""
    guild_id = GuildID(guild.id)
    settings = await guild_settings_manager.get_settings(guild_id)
    for ch in guild.text_channels:
        text = collector.collect_channel_topic(ch)
        settings.channel_guidelines[ChannelID(ch.id)] = text
    await guild_settings_manager.save(guild_id, settings)


guidelines_sync_scheduler = GenericSyncScheduler(
    name="GUIDELINES_SYNC",
    per_guild_coro=sync_all_channel_guidelines,
    get_interval=lambda: app_config.guidelines_sync_interval,
)