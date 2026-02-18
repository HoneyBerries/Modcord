"""
Repository for core guild_settings table.

Handles only the guild_settings table — no joins, no related data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import aiosqlite

from modcord.datatypes.discord_datatypes import GuildID
from modcord.util.logger import get_logger

logger = get_logger("guild_settings_repo")


@dataclass
class GuildSettingsRow:
    """Raw DB row for a guild's core settings."""
    guild_id: int
    ai_enabled: bool
    rules: str
    auto_warn_enabled: bool
    auto_delete_enabled: bool
    auto_timeout_enabled: bool
    auto_kick_enabled: bool
    auto_ban_enabled: bool
    auto_review_enabled: bool


class GuildSettingsRepository:
    """CRUD for the guild_settings table only."""

    async def get(
        self, conn: aiosqlite.Connection, guild_id: GuildID
    ) -> GuildSettingsRow | None:
        """Fetch a single guild's core settings row."""
        async with conn.execute(
            """
            SELECT guild_id, ai_enabled, rules,
                   auto_warn_enabled, auto_delete_enabled, auto_timeout_enabled,
                   auto_kick_enabled, auto_ban_enabled, auto_review_enabled
            FROM guild_settings
            WHERE guild_id = ?
            """,
            (int(guild_id),),
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            return None

        return GuildSettingsRow(
            guild_id=row[0],
            ai_enabled=bool(row[1]),
            rules=row[2] or "",
            auto_warn_enabled=bool(row[3]),
            auto_delete_enabled=bool(row[4]),
            auto_timeout_enabled=bool(row[5]),
            auto_kick_enabled=bool(row[6]),
            auto_ban_enabled=bool(row[7]),
            auto_review_enabled=bool(row[8]),
        )

    async def get_all(
        self, conn: aiosqlite.Connection
    ) -> Dict[int, GuildSettingsRow]:
        """Fetch all guilds' core settings rows keyed by guild_id int."""
        async with conn.execute(
            """
            SELECT guild_id, ai_enabled, rules,
                   auto_warn_enabled, auto_delete_enabled, auto_timeout_enabled,
                   auto_kick_enabled, auto_ban_enabled, auto_review_enabled
            FROM guild_settings
            """
        ) as cursor:
            rows = await cursor.fetchall()

        result: Dict[int, GuildSettingsRow] = {}
        for row in rows:
            result[row[0]] = GuildSettingsRow(
                guild_id=row[0],
                ai_enabled=bool(row[1]),
                rules=row[2] or "",
                auto_warn_enabled=bool(row[3]),
                auto_delete_enabled=bool(row[4]),
                auto_timeout_enabled=bool(row[5]),
                auto_kick_enabled=bool(row[6]),
                auto_ban_enabled=bool(row[7]),
                auto_review_enabled=bool(row[8]),
            )

        return result

    async def upsert(
        self, conn: aiosqlite.Connection, row: GuildSettingsRow
    ) -> None:
        """Insert or update a guild's core settings row."""
        await conn.execute(
            """
            INSERT INTO guild_settings (
                guild_id, ai_enabled, rules,
                auto_warn_enabled, auto_delete_enabled, auto_timeout_enabled,
                auto_kick_enabled, auto_ban_enabled, auto_review_enabled
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                ai_enabled           = excluded.ai_enabled,
                rules                = excluded.rules,
                auto_warn_enabled    = excluded.auto_warn_enabled,
                auto_delete_enabled  = excluded.auto_delete_enabled,
                auto_timeout_enabled = excluded.auto_timeout_enabled,
                auto_kick_enabled    = excluded.auto_kick_enabled,
                auto_ban_enabled     = excluded.auto_ban_enabled,
                auto_review_enabled  = excluded.auto_review_enabled
            """,
            (
                int(row.guild_id),
                1 if row.ai_enabled else 0,
                row.rules,
                1 if row.auto_warn_enabled else 0,
                1 if row.auto_delete_enabled else 0,
                1 if row.auto_timeout_enabled else 0,
                1 if row.auto_kick_enabled else 0,
                1 if row.auto_ban_enabled else 0,
                1 if row.auto_review_enabled else 0,
            ),
        )

    async def delete(
        self, conn: aiosqlite.Connection, guild_id: GuildID
    ) -> None:
        """Delete a guild row (CASCADE removes related rows)."""
        await conn.execute(
            "DELETE FROM guild_settings WHERE guild_id = ?",
            (int(guild_id),),
        )
