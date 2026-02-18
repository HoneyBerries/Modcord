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

from modcord.datatypes.discord_datatypes import GuildID
from modcord.datatypes.guild_settings import GuildSettings
from modcord.database.db_connection import db_connection
from modcord.database.database import database
from modcord.settings.repositories import (
    GuildSettingsRepository,
    ModeratorRolesRepository,
    ReviewChannelsRepository,
    ChannelGuidelinesRepository,
)
from modcord.settings.repositories.guild_settings_repo import GuildSettingsRow
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
        self._guild_settings_repo = GuildSettingsRepository()
        self._moderator_roles_repo = ModeratorRolesRepository()
        self._review_channels_repo = ReviewChannelsRepository()
        self._channel_guidelines_repo = ChannelGuidelinesRepository()
        # Per-guild locks: concurrent guilds don't block each other
        self._per_guild_locks: Dict[int, asyncio.Lock] = {}

    def _lock_for(self, guild_id: GuildID) -> asyncio.Lock:
        gid = guild_id.to_int()
        if gid not in self._per_guild_locks:
            self._per_guild_locks[gid] = asyncio.Lock()
        return self._per_guild_locks[gid]

    async def initialize(self) -> None:
        """Initialize the underlying database (schema creation)."""
        await database.initialize()
        logger.info("[GUILD SETTINGS SERVICE] Database initialized")

    # ------------------------------------------------------------------
    # Load
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

            # 2-4. Related tables — one query each, merges in Python
            roles_by_guild = await self._moderator_roles_repo.get_for_guilds(conn, guild_ids_int)
            channels_by_guild = await self._review_channels_repo.get_for_guilds(conn, guild_ids_int)
            guidelines_by_guild = await self._channel_guidelines_repo.get_for_guilds(conn, guild_ids_int)

        result: Dict[GuildID, GuildSettings] = {}
        for gid_int, core in core_rows.items():
            guild_id = GuildID.from_int(gid_int)
            settings = _row_to_settings(
                core,
                moderator_role_ids=roles_by_guild.get(gid_int, set()),
                review_channel_ids=channels_by_guild.get(gid_int, set()),
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

            roles = await self._moderator_roles_repo.get_for_guild(conn, guild_id)
            channels = await self._review_channels_repo.get_for_guild(conn, guild_id)
            guidelines = await self._channel_guidelines_repo.get_for_guild(conn, guild_id)

        return _row_to_settings(core, roles, channels, guidelines)

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
                    await self._moderator_roles_repo.replace(conn, guild_id, settings.moderator_role_ids)
                    await self._review_channels_repo.replace(conn, guild_id, settings.review_channel_ids)
                    await self._channel_guidelines_repo.replace(conn, guild_id, settings.channel_guidelines)
                    # transaction() auto-commits on clean exit

                logger.debug(
                    "[GUILD SETTINGS SERVICE] Persisted guild %s", guild_id.to_int()
                )
                return True
            except Exception:
                logger.exception(
                    "[GUILD SETTINGS SERVICE] Failed to persist guild %s", guild_id.to_int()
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
                # Moderation history has no FK, delete it explicitly
                await conn.execute(
                    "DELETE FROM moderation_actions WHERE guild_id = ?",
                    (guild_id.to_int(),),
                )
                # transaction() auto-commits on clean exit

            logger.debug(
                "[GUILD SETTINGS SERVICE] Deleted all data for guild %s", guild_id.to_int()
            )
            return True
        except Exception:
            logger.exception(
                "[GUILD SETTINGS SERVICE] Failed to delete guild %s", guild_id.to_int()
            )
            return False


# ------------------------------------------------------------------
# Private helpers — convert between GuildSettings ↔ repo rows
# ------------------------------------------------------------------

def _row_to_settings(
    core: GuildSettingsRow,
    moderator_role_ids,
    review_channel_ids,
    channel_guidelines,
) -> GuildSettings:
    """Build a GuildSettings from the raw repo rows."""
    settings = GuildSettings(guild_id=GuildID.from_int(core.guild_id))
    settings.ai_enabled = core.ai_enabled
    settings.rules = core.rules
    settings.auto_warn_enabled = core.auto_warn_enabled
    settings.auto_delete_enabled = core.auto_delete_enabled
    settings.auto_timeout_enabled = core.auto_timeout_enabled
    settings.auto_kick_enabled = core.auto_kick_enabled
    settings.auto_ban_enabled = core.auto_ban_enabled
    settings.auto_review_enabled = core.auto_review_enabled
    settings.moderator_role_ids = set(moderator_role_ids)
    settings.review_channel_ids = set(review_channel_ids)
    settings.channel_guidelines = dict(channel_guidelines)
    return settings


def _settings_to_row(guild_id: GuildID, settings: GuildSettings) -> GuildSettingsRow:
    """Build a GuildSettingsRow from a GuildSettings object."""
    return GuildSettingsRow(
        guild_id=guild_id.to_int(),
        ai_enabled=settings.ai_enabled,
        rules=settings.rules,
        auto_warn_enabled=settings.auto_warn_enabled,
        auto_delete_enabled=settings.auto_delete_enabled,
        auto_timeout_enabled=settings.auto_timeout_enabled,
        auto_kick_enabled=settings.auto_kick_enabled,
        auto_ban_enabled=settings.auto_ban_enabled,
        auto_review_enabled=settings.auto_review_enabled,
    )


# Singleton
guild_settings_service = GuildSettingsService()
