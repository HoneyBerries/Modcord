"""
GuildSettingsService — orchestrates multi-repository guild settings persistence.

Responsibilities:
- Load all guilds at startup using four separate targeted queries (no big joins)
- Persist a guild's complete settings in one atomic transaction
- Delete all guild data
- Per-guild async locks so two guilds can persist concurrently

All raw DB access is delegated to the four repositories.
The service never does SQL itself.
"""

from __future__ import annotations

import asyncio
from typing import Dict

from modcord.database.database import database
from modcord.database.db_connection import db_connection
from modcord.datatypes.discord_datatypes import GuildID
from modcord.datatypes.guild_settings import GuildSettings
from modcord.repositories.channel_guidelines_repo import ChannelGuidelinesRepository
from modcord.repositories.guild_options_repo import GuildSettingsRow, GuildOptionsRepository
from modcord.util.logger import get_logger

logger = get_logger("guild_settings_service")



class GuildSettingsService:
    """
    Orchestrates guild settings persistence across all four repositories.

    - No SQL here — only calls repos and handles transactions/locks.
    - Per-guild locks allow independent guilds to persist concurrently.
    - Uses four small targeted queries at startup instead of one big JOIN.
    """

    def __init__(self) -> None:
        self._guild_settings_repo = GuildOptionsRepository()
        self._channel_guidelines_repo = ChannelGuidelinesRepository()
        # Per-guild locks: concurrent guilds don't block each other
        self._per_guild_locks: Dict[int, asyncio.Lock] = {}

    def _lock_for(self, guild_id: GuildID) -> asyncio.Lock:
        gid = int(guild_id)
        if gid not in self._per_guild_locks:
            self._per_guild_locks[gid] = asyncio.Lock()
        return self._per_guild_locks[gid]

    async def initialize(self) -> None:
        """Initialize the underlying database (schema creation)."""
        await database.initialize()
        logger.info("[GUILD SETTINGS SERVICE] Database initialized")

    # ------------------------------------------------------------------
    # Load the DB
    # ------------------------------------------------------------------

    async def load_all(self) -> Dict[GuildID, GuildSettings]:
        """
        Load all guild settings using four small queries instead of one big JOIN.

        Returns a dict mapping GuildID → GuildSettings.
        """
        async with db_connection.read() as conn:
            # 1. Core settings (one row per guild)
            core_rows = await self._guild_settings_repo.get_all(conn)
            if not core_rows:
                return {}

            guild_ids_int = list(core_rows.keys())

            # 2. Related tables — one query each, merges in Python
            guidelines_by_guild = await self._channel_guidelines_repo.get_for_guilds(conn, guild_ids_int)

        result: Dict[GuildID, GuildSettings] = {}
        for gid_int, core in core_rows.items():
            guild_id = GuildID.from_int(gid_int)
            settings = _row_to_settings(
                core,
                channel_guidelines=guidelines_by_guild.get(gid_int, {}),
            )
            result[guild_id] = settings

        logger.info("[GUILD SETTINGS SERVICE] Loaded %d guilds from database", len(result))
        return result

    async def fetch(self, guild_id: GuildID) -> GuildSettings | None:
        """
        Load a single guild's complete settings.

        Returns None if the guild has no persisted settings.
        """
        async with db_connection.read() as conn:
            core = await self._guild_settings_repo.get(conn, guild_id)
            if core is None:
                return None

            guidelines = await self._channel_guidelines_repo.get_for_guild(conn, guild_id)

        return _row_to_settings(core, guidelines)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    async def save(self, guild_id: GuildID, settings: GuildSettings) -> bool:
        """
        Persist all settings for a guild in a single atomic transaction.

        Uses a per-guild lock so two simultaneous saves for the same guild
        are serialized, while different guilds proceed concurrently.
        """
        async with self._lock_for(guild_id):
            try:
                async with db_connection.transaction() as conn:
                    core_row = _settings_to_row(guild_id, settings)
                    await self._guild_settings_repo.upsert(conn, core_row)
                    await self._channel_guidelines_repo.replace(conn, guild_id, settings.channel_guidelines)
                    # transaction() auto-commits on clean exit

                logger.info(
                    "[GUILD SETTINGS SERVICE] Persisted guild %s", str(guild_id)
                )
                return True
            except Exception:
                logger.exception(
                    "[GUILD SETTINGS SERVICE] Failed to persist guild %s", str(guild_id)
                )
                return False

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete(self, guild_id: GuildID) -> bool:
        """
        Delete all data for a guild (settings + related tables via CASCADE).

        Also purges moderation action history for the guild.
        """
        try:
            async with db_connection.transaction() as conn:
                # CASCADE on guild_settings will remove roles/channels/guidelines
                await self._guild_settings_repo.delete(conn, guild_id)
                # transaction() auto-commits on clean exit

            logger.debug(
                "[GUILD SETTINGS SERVICE] Deleted all data for guild %s", str(guild_id)
            )
            return True
        except Exception:
            logger.exception(
                "[GUILD SETTINGS SERVICE] Failed to delete guild %s", str(guild_id)
            )
            return False


# ------------------------------------------------------------------
# Private helpers — convert between GuildSettings ↔ repo rows
# ------------------------------------------------------------------

def _row_to_settings(
    core: GuildSettingsRow,
    channel_guidelines,
) -> GuildSettings:
    """Build a GuildSettings from the raw repo rows."""
    from modcord.datatypes.discord_datatypes import ChannelID
    settings = GuildSettings(guild_id=GuildID.from_int(core.guild_id))
    settings.ai_enabled = core.ai_enabled
    settings.rules = core.rules
    settings.auto_warn_enabled = core.auto_warn_enabled
    settings.auto_delete_enabled = core.auto_delete_enabled
    settings.auto_timeout_enabled = core.auto_timeout_enabled
    settings.auto_kick_enabled = core.auto_kick_enabled
    settings.auto_ban_enabled = core.auto_ban_enabled
    settings.channel_guidelines = dict(channel_guidelines)
    settings.mod_log_channel_id = ChannelID(core.mod_log_channel_id) if core.mod_log_channel_id else None
    return settings


def _settings_to_row(guild_id: GuildID, settings: GuildSettings) -> GuildSettingsRow:
    """Build a GuildSettingsRow from a GuildSettings object."""
    return GuildSettingsRow(
        guild_id=int(guild_id),
        ai_enabled=settings.ai_enabled,
        rules=settings.rules,
        auto_warn_enabled=settings.auto_warn_enabled,
        auto_delete_enabled=settings.auto_delete_enabled,
        auto_timeout_enabled=settings.auto_timeout_enabled,
        auto_kick_enabled=settings.auto_kick_enabled,
        auto_ban_enabled=settings.auto_ban_enabled,
        mod_log_channel_id=int(settings.mod_log_channel_id) if settings.mod_log_channel_id else None,
    )


# Singleton
guild_settings_service = GuildSettingsService()
