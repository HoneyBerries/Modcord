"""
Persistent per-guild configuration storage for the moderation bot.

Provides a simplified API for managing guild settings:
- get(guild_id) -> GuildSettings: Retrieve settings (creates default if missing)
- update(guild_id, **kwargs): Update fields and auto-persist
- is_action_allowed/set_action_allowed: Action-type specific helpers
- save(guild_id): Explicit persist trigger

Database schema:
- guild_settings table with columns: guild_id, ai_enabled, rules, auto_*_enabled flags
- channel_guidelines table with columns: guild_id, channel_id, guidelines
"""

import asyncio
from typing import Any, Dict, List, Set

from modcord.datatypes.discord_datatypes import ChannelID, GuildID
from modcord.datatypes.action_datatypes import ActionType
from modcord.datatypes.guild_settings import GuildSettings, ACTION_FLAG_FIELDS
from modcord.util.logger import get_logger
from modcord.database.database import database

logger = get_logger("guild_settings_manager")


class GuildSettingsManager:
    """
    Manager for persistent per-guild settings.

    Provides a clean API:
    - get(guild_id): Retrieve settings object
    - update(guild_id, **kwargs): Update fields and auto-persist
    - is_action_allowed/set_action_allowed: ActionType helpers
    - save(guild_id): Explicit persist
    """

    def __init__(self):
        """Instantiate caches and persistence helpers."""
        self._guilds: Dict[GuildID, GuildSettings] = {}
        self._persist_lock = asyncio.Lock()
        self._active_persists: Set[asyncio.Task] = set()
        self._db_initialized = False

        logger.info("[GUILD SETTINGS MANAGER] Initialized")

    async def async_init(self) -> None:
        """Initialize the database and load settings from disk."""
        if not self._db_initialized:
            await database.initialize()
            await self._load_from_disk()
            self._db_initialized = True
            logger.info("[GUILD SETTINGS MANAGER] Database initialized and settings loaded")

    # ========== Core API ==========

    def get(self, guild_id: GuildID) -> GuildSettings:
        """
        Retrieve settings for a guild, creating defaults if missing.

        Args:
            guild_id: The guild ID to fetch settings for.

        Returns:
            GuildSettings instance for the guild.
        """
        if not isinstance(guild_id, GuildID):
            guild_id = GuildID(guild_id)
        
        settings = self._guilds.get(guild_id)
        if settings is None:
            settings = GuildSettings(guild_id=guild_id)
            self._guilds[guild_id] = settings
        return settings

    def update(self, guild_id: GuildID, **kwargs: Any) -> GuildSettings:
        """
        Update settings fields and auto-persist.

        Args:
            guild_id: The guild ID to update settings for.
            **kwargs: Field names and values to update (e.g., ai_enabled=True, rules="...")

        Returns:
            Updated GuildSettings instance.
        """
        if not isinstance(guild_id, GuildID):
            guild_id = GuildID(guild_id)
        
        settings = self.get(guild_id)
        
        for field_name, value in kwargs.items():
            if hasattr(settings, field_name):
                setattr(settings, field_name, value)
            else:
                logger.warning(
                    "[GUILD SETTINGS MANAGER] Unknown field %s for guild %s",
                    field_name, guild_id.to_int()
                )
        
        self.save(guild_id)
        return settings

    def save(self, guild_id: GuildID) -> None:
        """
        Schedule persistence of guild settings to database.

        Args:
            guild_id: The guild ID to persist.
        """
        if not isinstance(guild_id, GuildID):
            guild_id = GuildID(guild_id)
        
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning(
                "[GUILD SETTINGS MANAGER] Cannot persist guild %s: no running event loop",
                guild_id.to_int()
            )
            return

        task = loop.create_task(self._persist_guild(guild_id))
        self._active_persists.add(task)

        def _cleanup(completed: asyncio.Task) -> None:
            self._active_persists.discard(completed)
            try:
                if not completed.result():
                    logger.error(
                        "[GUILD SETTINGS MANAGER] Failed to persist guild %s",
                        guild_id.to_int()
                    )
            except Exception:
                logger.exception("Error persisting guild %s", guild_id.to_int())

        task.add_done_callback(_cleanup)

    def list_guild_ids(self) -> List[GuildID]:
        """Return a snapshot list of guild IDs currently cached."""
        return list(self._guilds.keys())

    # ========== Action Type Helpers ==========

    def is_action_allowed(self, guild_id: GuildID, action: ActionType) -> bool:
        """
        Check if a specific action type is enabled for the guild.

        Args:
            guild_id: The guild ID.
            action: The ActionType to check.

        Returns:
            True if the action is allowed, False otherwise.
        """
        settings = self.get(guild_id)
        field_name = ACTION_FLAG_FIELDS.get(action)
        if field_name is None:
            return True
        return bool(getattr(settings, field_name, True))

    def set_action_allowed(self, guild_id: GuildID, action: ActionType, enabled: bool) -> bool:
        """
        Enable or disable an action type for the guild and auto-persist.

        Args:
            guild_id: The guild ID.
            action: The ActionType to toggle.
            enabled: Whether to enable or disable.

        Returns:
            True if successful, False if action type is unsupported.
        """
        field_name = ACTION_FLAG_FIELDS.get(action)
        if field_name is None:
            logger.warning(
                "[GUILD SETTINGS MANAGER] Unsupported action %s for guild %s",
                action, guild_id
            )
            return False

        self.update(guild_id, **{field_name: bool(enabled)})
        return True

    # ========== Lifecycle ==========

    async def shutdown(self) -> None:
        """Await any pending persistence tasks during shutdown."""
        pending = list(self._active_persists)
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self._active_persists.clear()
        logger.info("[GUILD SETTINGS MANAGER] Shutdown complete")

    # ========== Private Methods ==========

    async def _load_from_disk(self) -> bool:
        """Load persisted guild settings from database into memory."""
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

                self._guilds.clear()
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
                        self._guilds[guild_id] = settings
                        guild_seen.add(guild_id)

                    settings = self._guilds[guild_id]

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
                    "[GUILD SETTINGS MANAGER] Loaded %d guild settings from database",
                    len(self._guilds)
                )
                return True
        except Exception:
            logger.exception("[GUILD SETTINGS MANAGER] Failed to load from database")
            return False

    async def _persist_guild(self, guild_id: GuildID) -> bool:
        """Persist a single guild's settings to database."""
        settings = self._guilds.get(guild_id)
        if settings is None:
            logger.warning(
                "[GUILD SETTINGS MANAGER] Cannot persist guild %s: not in cache",
                guild_id.to_int()
            )
            return False

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
                        "[GUILD SETTINGS MANAGER] Persisted guild %s to database",
                        guild_id.to_int()
                    )
                    return True
            except Exception:
                logger.exception(
                    "[GUILD SETTINGS MANAGER] Failed to persist guild %s",
                    guild_id.to_int()
                )
                return False


# Global instance
guild_settings_manager = GuildSettingsManager()
