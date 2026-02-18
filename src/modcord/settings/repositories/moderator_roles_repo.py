"""
Repository for the guild_moderator_roles table.
"""

from __future__ import annotations

from typing import Dict, List, Set

import aiosqlite

from modcord.datatypes.discord_datatypes import GuildID
from modcord.util.logger import get_logger

logger = get_logger("moderator_roles_repo")


class ModeratorRolesRepository:
    """CRUD for the guild_moderator_roles table."""

    async def get_for_guild(
        self, conn: aiosqlite.Connection, guild_id: GuildID
    ) -> Set[int]:
        """Return all moderator role IDs for a single guild."""
        async with conn.execute(
            "SELECT role_id FROM guild_moderator_roles WHERE guild_id = ?",
            (int(guild_id),),
        ) as cursor:
            rows = await cursor.fetchall()
        return {row[0] for row in rows}

    async def get_for_guilds(
        self, conn: aiosqlite.Connection, guild_ids: List[int]
    ) -> Dict[int, Set[int]]:
        """Return moderator role IDs for multiple guilds in one query."""
        if not guild_ids:
            return {}

        placeholders = ",".join("?" * len(guild_ids))
        async with conn.execute(
            f"SELECT guild_id, role_id FROM guild_moderator_roles WHERE guild_id IN ({placeholders})",
            guild_ids,
        ) as cursor:
            rows = await cursor.fetchall()

        result: Dict[int, Set[int]] = {gid: set() for gid in guild_ids}
        for guild_id_int, role_id in rows:
            result[guild_id_int].add(role_id)
        return result

    async def replace(
        self, conn: aiosqlite.Connection, guild_id: GuildID, role_ids: Set[int]
    ) -> None:
        """Replace all moderator roles for a guild atomically."""
        gid = int(guild_id)
        await conn.execute(
            "DELETE FROM guild_moderator_roles WHERE guild_id = ?", (gid,)
        )
        if role_ids:
            await conn.executemany(
                "INSERT INTO guild_moderator_roles (guild_id, role_id) VALUES (?, ?)",
                [(gid, rid) for rid in role_ids],
            )
