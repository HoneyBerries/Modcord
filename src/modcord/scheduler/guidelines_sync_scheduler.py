"""Scheduler for periodic synchronization of channel guidelines across all guilds."""

from __future__ import annotations

from modcord.configuration.app_configuration import app_config
from modcord.moderation.channel_guidelines_injection_engine import channel_guidelines_injection_engine
from modcord.scheduler.generic_sync_scheduler import GenericSyncScheduler

guidelines_sync_scheduler = GenericSyncScheduler(
    name="GUIDELINES_SYNC",
    per_guild_coro=channel_guidelines_injection_engine.sync_all_channel_guidelines,
    get_interval=lambda: app_config.guidelines_sync_interval,
)