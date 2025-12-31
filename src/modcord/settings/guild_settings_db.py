"""
Database access layer for guild settings.

Handles all database operations for persisting and retrieving guild configuration:
- load_all_guild_settings(): Load all guilds from database
- save_guild_settings(): Persist a guild's settings
- delete_guild_data(): Delete all data for a guild
"""

import asyncio
from typing import Dict, Set

from modcord.datatypes.discord_datatypes import ChannelID, GuildID
from modcord.datatypes.guild_settings import GuildSettings
from modcord.util.logger import get_logger
from modcord.database.database import database

logger = get_logger("guild_settings_db")


class GuildSettingsDB:
    """Database access layer for guild settings."""

    def __init__(self):
        """Initialize the database layer."""
        self._persist_lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize the database connection."""
        await database.initialize()
        logger.info("[GUILD SETTINGS DB] Database initialized")

    async def load_all_guild_settings(self) -> Dict[GuildID, GuildSettings]:
        """
        Load all persisted guild settings from database.

        Returns:
            Dictionary mapping guild IDs to GuildSettings objects.
        """
        guilds: Dict[GuildID, GuildSettings] = {}
        
        try:
            async with database.get_connection() as conn:
                async with conn.execute("""
                    SELECT 
                        gs.guild_id, gs.ai_enabled, gs.rules,
                        gs.auto_warn_enabled, gs.auto_delete_enabled,
                        gs.auto_timeout_enabled, gs.auto_kick_enabled, gs.auto_ban_enabled,
                        gs.auto_review_enabled,
                        mr.role_id,
                        rc.channel_id,
                        cg.channel_id, cg.guidelines
                    FROM guild_settings gs
                    LEFT JOIN guild_moderator_roles mr ON gs.guild_id = mr.guild_id
                    LEFT JOIN guild_review_channels rc ON gs.guild_id = rc.guild_id
                    LEFT JOIN channel_guidelines cg ON gs.guild_id = cg.guild_id
                    ORDER BY gs.guild_id
                """) as cursor:
                    rows = await cursor.fetchall()

                guild_seen: Set[GuildID] = set()

                for row in rows:
                    guild_id = GuildID.from_int(row[0])
                    
                    if guild_id not in guild_seen:
                        settings = GuildSettings(
                            guild_id=guild_id,
                            ai_enabled=bool(row[1]),
                            rules=row[2] or "",
                            auto_warn_enabled=bool(row[3]),
                            auto_delete_enabled=bool(row[4]),
                            auto_timeout_enabled=bool(row[5]),
                            auto_kick_enabled=bool(row[6]),
                            auto_ban_enabled=bool(row[7]),
                            auto_review_enabled=bool(row[8]) if row[8] is not None else True,
                            moderator_role_ids=[],
                            review_channel_ids=[],
                            channel_guidelines={},
                        )
                        guilds[guild_id] = settings
                        guild_seen.add(guild_id)

                    settings = guilds[guild_id]

                    # Add moderator role if present
                    if row[9] is not None and row[9] not in settings.moderator_role_ids:
                        settings.moderator_role_ids.append(row[9])

                    # Add review channel if present
                    if row[10] is not None:
                        channel_obj = ChannelID.from_int(row[10])
                        if channel_obj not in settings.review_channel_ids:
                            settings.review_channel_ids.append(channel_obj)

                    # Add channel guidelines if present
                    if row[11] is not None and row[12] is not None:
                        channel_obj = ChannelID.from_int(row[11])
                        settings.channel_guidelines[channel_obj] = row[12]

                logger.info(
                    "[GUILD SETTINGS DB] Loaded %d guild settings from database",
                    len(guilds)
                )
                return guilds
        except Exception:
            logger.exception("[GUILD SETTINGS DB] Failed to load from database")
            return {}

    async def save_guild_settings(self, guild_id: GuildID, settings: GuildSettings) -> bool:
        """
        Persist a single guild's settings to database.

        Args:
            guild_id: The guild ID to persist.
            settings: The GuildSettings object to save.

        Returns:
            True if successful, False otherwise.
        """
        async with self._persist_lock:
            try:
                async with database.get_connection() as conn:
                    # Persist main guild settings
                    await conn.execute("""
                        INSERT INTO guild_settings (
                            guild_id, ai_enabled, rules,
                            auto_warn_enabled, auto_delete_enabled,
                            auto_timeout_enabled, auto_kick_enabled, auto_ban_enabled,
                            auto_review_enabled
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(guild_id) DO UPDATE SET
                            ai_enabled = excluded.ai_enabled,
                            rules = excluded.rules,
                            auto_warn_enabled = excluded.auto_warn_enabled,
                            auto_delete_enabled = excluded.auto_delete_enabled,
                            auto_timeout_enabled = excluded.auto_timeout_enabled,
                            auto_kick_enabled = excluded.auto_kick_enabled,
                            auto_ban_enabled = excluded.auto_ban_enabled,
                            auto_review_enabled = excluded.auto_review_enabled
                    """, (
                        guild_id.to_int(),
                        1 if settings.ai_enabled else 0,
                        settings.rules,
                        1 if settings.auto_warn_enabled else 0,
                        1 if settings.auto_delete_enabled else 0,
                        1 if settings.auto_timeout_enabled else 0,
                        1 if settings.auto_kick_enabled else 0,
                        1 if settings.auto_ban_enabled else 0,
                        1 if settings.auto_review_enabled else 0,
                    ))

                    # Persist moderator roles
                    await conn.execute(
                        "DELETE FROM guild_moderator_roles WHERE guild_id = ?",
                        (guild_id.to_int(),)
                    )
                    for role_id in settings.moderator_role_ids:
                        await conn.execute(
                            "INSERT INTO guild_moderator_roles (guild_id, role_id) VALUES (?, ?)",
                            (guild_id.to_int(), role_id)
                        )

                    # Persist review channels
                    await conn.execute(
                        "DELETE FROM guild_review_channels WHERE guild_id = ?",
                        (guild_id.to_int(),)
                    )
                    for channel_id in settings.review_channel_ids:
                        channel_obj = ChannelID(channel_id)
                        await conn.execute(
                            "INSERT INTO guild_review_channels (guild_id, channel_id) VALUES (?, ?)",
                            (guild_id.to_int(), channel_obj.to_int())
                        )

                    # Persist channel guidelines
                    await conn.execute(
                        "DELETE FROM channel_guidelines WHERE guild_id = ?",
                        (guild_id.to_int(),)
                    )
                    for channel_id, guidelines in settings.channel_guidelines.items():
                        channel_obj = ChannelID(channel_id)
                        await conn.execute(
                            "INSERT INTO channel_guidelines (guild_id, channel_id, guidelines) VALUES (?, ?, ?)",
                            (guild_id.to_int(), channel_obj.to_int(), guidelines)
                        )

                    await conn.commit()
                    logger.debug(
                        "[GUILD SETTINGS DB] Persisted guild %s to database",
                        guild_id.to_int()
                    )
                    return True
            except Exception:
                logger.exception(
                    "[GUILD SETTINGS DB] Failed to persist guild %s",
                    guild_id.to_int()
                )
                return False

    async def delete_guild_data(self, guild_id: GuildID) -> bool:
        """
        Delete all data for a guild from database.

        This removes:
        - Guild settings
        - Moderator roles
        - Review channels
        - Channel guidelines
        - Moderation action history

        Args:
            guild_id: The guild ID to delete.

        Returns:
            True if successful, False otherwise.
        """
        try:
            async with database.get_connection() as conn:
                # Delete main guild settings (CASCADE will handle related tables)
                await conn.execute(
                    "DELETE FROM guild_settings WHERE guild_id = ?",
                    (guild_id.to_int(),)
                )

                # Also delete moderation history for this guild
                await conn.execute(
                    "DELETE FROM moderation_actions WHERE guild_id = ?",
                    (guild_id.to_int(),)
                )

                await conn.commit()
                logger.debug(
                    f"[GUILD SETTINGS DB] Deleted all data for guild {guild_id.to_int()} from database"
                )
                return True
        except Exception:
            logger.exception(
                f"[GUILD SETTINGS DB] Failed to delete guild {guild_id.to_int()} from database"
            )
            return False