"""
Repository for the generic_channel_guidelines table.
"""

from __future__ import annotations

from typing import Dict, List

import aiosqlite

from modcord.datatypes.discord_datatypes import GuildID, ChannelID
from modcord.util.logger import get_logger

logger = get_logger("channel_guidelines_repo")


class ChannelGuidelinesRepository:
    """CRUD for the generic_channel_guidelines table."""

    @staticmethod
    async def get_for_guild(
            conn: aiosqlite.Connection, guild_id: GuildID
    ) -> Dict[ChannelID, str]:
        """Return all channel guidelines for a single guild."""
        async with conn.execute(
            "SELECT channel_id, guidelines FROM generic_channel_guidelines WHERE guild_id = ?",
            (int(guild_id),),
        ) as cursor:
            rows = await cursor.fetchall()
        return {ChannelID.from_int(row[0]): row[1] for row in rows}

    @staticmethod
    async def get_for_guilds(
            conn: aiosqlite.Connection, guild_ids: List[int]
    ) -> Dict[int, Dict[ChannelID, str]]:
        """Return channel guidelines for multiple guilds in one query."""
        if not guild_ids:
            return {}

        placeholders = ",".join("?" * len(guild_ids))
        async with conn.execute(
            f"SELECT guild_id, channel_id, guidelines FROM generic_channel_guidelines WHERE guild_id IN ({placeholders})",
            guild_ids,
        ) as cursor:
            rows = await cursor.fetchall()

        result: Dict[int, Dict[ChannelID, str]] = {gid: {} for gid in guild_ids}
        for guild_id_int, channel_id_int, guidelines in rows:
            result[guild_id_int][ChannelID.from_int(channel_id_int)] = guidelines
        return result

    @staticmethod
    async def replace(
            conn: aiosqlite.Connection,
        guild_id: GuildID,
        guidelines: Dict[ChannelID, str],
    ) -> None:
        """Replace all channel guidelines for a guild atomically."""
        gid = int(guild_id)
        await conn.execute(
            "DELETE FROM generic_channel_guidelines WHERE guild_id = ?", (gid,)
        )
        if guidelines:
            await conn.executemany(
                "INSERT INTO generic_channel_guidelines (guild_id, channel_id, guidelines) VALUES (?, ?, ?)",
                [(gid, int(ch), text) for ch, text in guidelines.items()],
            )
