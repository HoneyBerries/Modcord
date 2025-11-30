"""Scheduler for periodic synchronization of server rules across all guilds."""

from __future__ import annotations

from modcord.configuration.app_configuration import app_config
from modcord.moderation import rules_injection_engine as rules_engine
from modcord.scheduler.generic_sync_scheduler import GenericSyncScheduler

rules_sync_scheduler = GenericSyncScheduler(
    name="RULES_SYNC",
    per_guild_coro=rules_engine.rules_injection_engine.sync_guild_rules,
    get_interval=lambda: app_config.rules_sync_interval,
)