"""
Persistent storage for scheduled temporary bans.

Timestamps are stored as INTEGER unix seconds (seconds since the epoch)
so comparisons are trivial and there is no string parsing or timezone
conversion needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import aiosqlite

from modcord.util.logger import get_logger

logger = get_logger("tempban_storage")


@dataclass
class TemporaryBanRecord:
    """A single row from the ``temporary_bans`` table."""
    guild_id: int
    user_id: str
    unban_at: int   # unix seconds (UTC)
    reason: str


class TemporaryBanRepo:
    """Low-level CRUD for the ``temporary_bans`` table."""

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    @staticmethod
    async def upsert(
        conn: aiosqlite.Connection,
        guild_id: int,
        user_id: str,
        unban_at: int,
        reason: str,
    ) -> None:
        """Insert or replace a tempban row (primary key = guild_id + user_id)."""
        await conn.execute(
            """
            INSERT INTO temporary_bans (guild_id, user_id, unban_at, reason)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                unban_at = excluded.unban_at,
                reason   = excluded.reason
            """,
            (guild_id, str(user_id), unban_at, reason),
        )

    @staticmethod
    async def delete(
        conn: aiosqlite.Connection,
        guild_id: int,
        user_id: str,
    ) -> None:
        """Remove a tempban row after the ban has been lifted (or cancelled)."""
        await conn.execute(
            "DELETE FROM temporary_bans WHERE guild_id = ? AND user_id = ?",
            (guild_id, str(user_id)),
        )

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    @staticmethod
    async def get_expired(
        conn: aiosqlite.Connection,
        now: int,
    ) -> List[TemporaryBanRecord]:
        """Return all rows where ``unban_at <= now`` (unix seconds)."""
        cursor = await conn.execute(
            "SELECT guild_id, user_id, unban_at, reason "
            "FROM temporary_bans WHERE unban_at <= ?",
            (now,),
        )
        rows = await cursor.fetchall()
        return [
            TemporaryBanRecord(
                guild_id=row[0],
                user_id=str(row[1]),
                unban_at=row[2],
                reason=row[3],
            )
            for row in rows
        ]

    @staticmethod
    async def exists(
        conn: aiosqlite.Connection,
        guild_id: int,
        user_id: str,
    ) -> bool:
        """Return True if a pending tempban exists for the given user."""
        cursor = await conn.execute(
            "SELECT 1 FROM temporary_bans WHERE guild_id = ? AND user_id = ? LIMIT 1",
            (guild_id, str(user_id)),
        )
        return await cursor.fetchone() is not None


# Module-level singleton
tempban_storage = TemporaryBanRepo()

