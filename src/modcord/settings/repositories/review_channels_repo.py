"""
Repository for the guild_review_channels table.
"""

from __future__ import annotations

from typing import Dict, List, Set

import aiosqlite

from modcord.datatypes.discord_datatypes import GuildID, ChannelID
from modcord.util.logger import get_logger

logger = get_logger("review_channels_repo")


class ReviewChannelsRepository:
    """CRUD for the guild_review_channels table."""

    async def get_for_guild(
        self, conn: aiosqlite.Connection, guild_id: GuildID
    ) -> Set[ChannelID]:
        """Return all review channel IDs for a single guild."""
        async with conn.execute(
            "SELECT channel_id FROM guild_review_channels WHERE guild_id = ?",
            (guild_id.to_int(),),
        ) as cursor:
            rows = await cursor.fetchall()
        return {ChannelID.from_int(row[0]) for row in rows}

    async def get_for_guilds(
        self, conn: aiosqlite.Connection, guild_ids: List[int]
    ) -> Dict[int, Set[ChannelID]]:
        """Return review channel IDs for multiple guilds in one query."""
        if not guild_ids:
            return {}

        placeholders = ",".join("?" * len(guild_ids))
        async with conn.execute(
            f"SELECT guild_id, channel_id FROM guild_review_channels WHERE guild_id IN ({placeholders})",
            guild_ids,
        ) as cursor:
            rows = await cursor.fetchall()

        result: Dict[int, Set[ChannelID]] = {gid: set() for gid in guild_ids}
        for guild_id_int, channel_id_int in rows:
            result[guild_id_int].add(ChannelID.from_int(channel_id_int))
        return result

    async def replace(
        self, conn: aiosqlite.Connection, guild_id: GuildID, channel_ids: Set[ChannelID]
    ) -> None:
        """Replace all review channels for a guild atomically."""
        gid = guild_id.to_int()
        await conn.execute(
            "DELETE FROM guild_review_channels WHERE guild_id = ?", (gid,)
        )
        if channel_ids:
            await conn.executemany(
                "INSERT INTO guild_review_channels (guild_id, channel_id) VALUES (?, ?)",
                [(gid, ch.to_int()) for ch in channel_ids],
            )
