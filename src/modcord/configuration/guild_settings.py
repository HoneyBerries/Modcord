"""
Persistent per-guild configuration storage for the moderation bot.

Responsibilities:
- Persist per-guild settings (ai_enabled, rules, and action toggles) to SQLite database
- Cache server rules and per-channel guideline overrides in memory

Database schema:
- guild_settings table with columns: guild_id, ai_enabled, rules, auto_*_enabled flags
"""

import collections
import asyncio
from typing import Dict, DefaultDict, List, Set
from dataclasses import dataclass, field
from modcord.datatypes.discord_datatypes import ChannelID, GuildID
from modcord.datatypes.action_datatypes import ActionType
from modcord.util.logger import get_logger
from modcord.database.database import get_db
import discord

logger = get_logger("guild_settings_manager")


@dataclass(slots=True)
class GuildSettings:
    """Persistent per-guild configuration values."""

    guild_id: GuildID
    ai_enabled: bool = True
    rules: str = ""
    auto_warn_enabled: bool = True
    auto_delete_enabled: bool = True
    auto_timeout_enabled: bool = True
    auto_kick_enabled: bool = True
    auto_ban_enabled: bool = True
    auto_review_enabled: bool = True
    moderator_role_ids: List[int] = field(default_factory=list)
    review_channel_ids: List[ChannelID] = field(default_factory=list)


ACTION_FLAG_FIELDS: dict[ActionType, str] = {
    ActionType.WARN: "auto_warn_enabled",
    ActionType.DELETE: "auto_delete_enabled",
    ActionType.TIMEOUT: "auto_timeout_enabled",
    ActionType.KICK: "auto_kick_enabled",
    ActionType.BAN: "auto_ban_enabled",
    ActionType.REVIEW: "auto_review_enabled",
}


class GuildSettingsManager:
    """
    Manager for persistent per-guild settings and in-memory guideline overrides.

    Responsibilities:
    - Persist per-guild settings (ai_enabled, rules, action toggles) to SQLite database
    - Cache server rules and per-channel guideline overrides for quick access
    """

    def __init__(self):
        """Instantiate caches and persistence helpers."""
        # Persisted guild settings registry (guild_id -> GuildSettings)
        self.guilds: Dict[GuildID, GuildSettings] = {}

        # Channel-specific guidelines cache (guild_id -> channel_id -> guidelines_text)
        self.channel_guidelines: DefaultDict[GuildID, Dict[ChannelID, str]] = collections.defaultdict(dict)

        # Persistence helpers
        self._persist_lock = asyncio.Lock()
        self._active_persists: Set[asyncio.Task] = set()
        self._db_initialized = False

        logger.info("[GUILD SETTINGS MANAGER] Guild settings manager initialized")

    async def async_init(self) -> None:
        """Initialize the database and load settings from disk (async)."""
        if not self._db_initialized:
            await get_db().initialize_database()
            await self.load_from_disk()
            self._db_initialized = True
            logger.info("[GUILD SETTINGS MANAGER] Database initialized and settings loaded")

    def ensure_guild(self, guild_id: GuildID) -> GuildSettings:
        """Create default settings for a guild if none exist and return the record."""
        settings = self.guilds.get(guild_id)
        if settings is None:
            settings = GuildSettings(guild_id=guild_id)
            self.guilds[guild_id] = settings
        return settings

    def get_guild_settings(self, guild_id: GuildID) -> GuildSettings:
        """Fetch the cached :class:`GuildSettings` instance for the given guild."""
        return self.ensure_guild(guild_id)

    def list_guild_ids(self) -> List[GuildID]:
        """Return a snapshot list of guild IDs currently cached in memory."""
        return list(self.guilds.keys())

    def get_server_rules(self, guild_id: GuildID) -> str:
        """Return cached rules for a guild or an empty string."""
        settings = self.guilds.get(guild_id)
        return settings.rules if settings else ""

    def set_server_rules(self, guild_id: GuildID, rules: str) -> None:
        """
        Cache and persist rules for the given guild.

        Persistence is scheduled in a non-blocking manner.
        """
        if rules is None:
            rules = ""

        settings = self.ensure_guild(guild_id)
        settings.rules = rules
        logger.debug(f"[GUILD SETTINGS MANAGER] Updated rules cache for guild {guild_id.to_int()} (len={len(rules)})")

        self._trigger_persist(guild_id)
    def get_channel_guidelines(self, guild_id: GuildID, channel_id: ChannelID) -> str:
        """Return cached channel-specific guidelines or an empty string."""
        return self.channel_guidelines.get(guild_id, {}).get(channel_id, "")

    def set_channel_guidelines(self, guild_id: GuildID, channel_id: ChannelID, guidelines: str) -> None:
        """
        Cache and persist channel-specific guidelines.

        Persistence is scheduled in a non-blocking manner.
        """
        if guidelines is None:
            guidelines = ""

        if guild_id not in self.channel_guidelines:
            self.channel_guidelines[guild_id] = {}
        
        self.channel_guidelines[guild_id][channel_id] = guidelines
        logger.debug(
            "[GUILD SETTINGS MANAGER] Updated channel guidelines cache for guild %s, channel %s (len=%d)",
            guild_id.to_int(), channel_id.to_int(), len(guidelines)
        )

        self._trigger_persist_channel_guidelines(guild_id, channel_id)

    def _trigger_persist(self, guild_id: GuildID) -> None:
        """Schedule a best-effort persist of a single guild's settings to database."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("[GUILD SETTINGS MANAGER] Cannot persist guild %s: no running event loop", guild_id.to_int())
            return

        task = loop.create_task(self._persist_guild_async(guild_id))
        self._active_persists.add(task)

        def _cleanup(completed: asyncio.Task) -> None:
            self._active_persists.discard(completed)
            try:
                if not completed.result():
                    logger.error("[GUILD SETTINGS MANAGER] Failed to persist guild %s to database", guild_id.to_int())
            except Exception:
                logger.exception("Error while persisting guild %s to database", guild_id.to_int())

        task.add_done_callback(_cleanup)


    def _trigger_persist_channel_guidelines(self, guild_id: GuildID, channel_id: ChannelID) -> None:
        """Schedule a best-effort persist of channel guidelines to database."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning(
                "[GUILD SETTINGS MANAGER] Cannot persist channel guidelines for guild %s, channel %s: no running event loop",
                guild_id,
                channel_id
            )
            return

        task = loop.create_task(self._persist_channel_guidelines_async(guild_id, channel_id))
        self._active_persists.add(task)

        def _cleanup(completed: asyncio.Task) -> None:
            self._active_persists.discard(completed)
            try:
                if not completed.result():
                    logger.error(
                        "[GUILD SETTINGS MANAGER] Failed to persist channel guidelines for guild %s, channel %s",
                        guild_id,
                        channel_id
                    )
            except Exception:
                logger.exception(
                    "Error while persisting channel guidelines for guild %s, channel %s",
                    guild_id,
                    channel_id
                )

        task.add_done_callback(_cleanup)


    async def shutdown(self) -> None:
        """Await any pending persistence tasks during shutdown."""
        pending = list(self._active_persists)
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self._active_persists.clear()

        logger.info("[GUILD SETTINGS MANAGER] Guild settings manager shutdown complete")


    # --- AI moderation enable/disable ---
    def is_ai_enabled(self, guild_id: GuildID) -> bool:
        """Return True if AI moderation is enabled for the guild (default True)."""
        settings = self.guilds.get(guild_id)
        return settings.ai_enabled if settings else True


    def set_ai_enabled(self, guild_id: GuildID, enabled: bool) -> bool:
        """
        Set and persist the AI moderation enabled state for a guild.
        Return whether scheduling the persist was successful or not.
        """
        settings = self.ensure_guild(guild_id)
        settings.ai_enabled = bool(enabled)
        state = "enabled" if enabled else "disabled"
        logger.debug("[GUILD SETTINGS MANAGER] AI moderation %s for guild %s", state, guild_id.to_int())

        self._trigger_persist(guild_id)
        return True

    def is_action_allowed(self, guild_id: GuildID, action: ActionType) -> bool:
        """Return whether the specified AI action is allowed for the guild."""
        settings = self.ensure_guild(guild_id)
        field_name = ACTION_FLAG_FIELDS.get(action)
        if field_name is None:
            return True
        return bool(getattr(settings, field_name, True))
    

    def set_action_allowed(self, guild_id: GuildID, action: ActionType, enabled: bool) -> bool:
        """Enable or disable an AI action for the guild and persist the change."""
        guild_id_int = guild_id.to_int()
        field_name = ACTION_FLAG_FIELDS.get(action)
        if field_name is None:
            logger.warning("[GUILD SETTINGS MANAGER] Attempted to toggle unsupported action %s for guild %s", action, guild_id_int)
            return False

        settings = self.ensure_guild(guild_id)
        setattr(settings, field_name, bool(enabled))
        logger.debug(
            "[GUILD SETTINGS MANAGER] Set %s to %s for guild %s",
            field_name,
            enabled,
            guild_id_int,
        )
        self._trigger_persist(guild_id)
        return True


    # -------- Persistence helpers --------
    async def _persist_guild_async(self, guild_id: GuildID) -> bool:
        """
        Persist a single guild's settings to the database asynchronously.

        Args:
            guild_id: The guild ID to persist

        Returns:
            bool: True if successful, False otherwise
        """
        settings = self.guilds.get(guild_id)
        if settings is None:
            logger.warning("[GUILD SETTINGS MANAGER] Cannot persist guild %s: not in cache", guild_id.to_int())
            return False

        async with self._persist_lock:
            try:
                async with get_db().get_connection() as db:
                    # Persist main guild settings
                    await db.execute("""
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
                    
                    # Persist moderator roles - delete and reinsert for simplicity
                    await db.execute("DELETE FROM guild_moderator_roles WHERE guild_id = ?", (guild_id.to_int(),))
                    for role_id in settings.moderator_role_ids:
                        await db.execute(
                            "INSERT INTO guild_moderator_roles (guild_id, role_id) VALUES (?, ?)",
                            (guild_id.to_int(), role_id)
                        )
                    
                    # Persist review channels - delete and reinsert for simplicity
                    await db.execute("DELETE FROM guild_review_channels WHERE guild_id = ?", (guild_id.to_int(),))
                    for channel_id in settings.review_channel_ids:
                        channel_id_int = channel_id.to_int()
                        await db.execute(
                            "INSERT INTO guild_review_channels (guild_id, channel_id) VALUES (?, ?)",
                            (guild_id.to_int(), channel_id_int)
                        )
                    
                    await db.commit()
                    logger.debug("[GUILD SETTINGS MANAGER] Persisted guild %s to database", guild_id.to_int())
                    return True
            except Exception:
                logger.exception("[GUILD SETTINGS MANAGER] Failed to persist guild %s to database", guild_id.to_int())
                return False

    async def _persist_channel_guidelines_async(self, guild_id: GuildID, channel_id: ChannelID) -> bool:
        """
        Persist channel-specific guidelines to the database asynchronously.

        Args:
            guild_id: The guild ID
            channel_id: The channel ID

        Returns:
            bool: True if successful, False otherwise
        """
        guidelines = self.channel_guidelines.get(guild_id, {}).get(channel_id)
        if guidelines is None:
            logger.warning(
                "[GUILD SETTINGS MANAGER] Cannot persist channel guidelines for guild %s, channel %s: not in cache",
                guild_id,
                channel_id
            )
            return False

        async with self._persist_lock:
            try:
                async with get_db().get_connection() as db:
                    await db.execute("""
                        INSERT INTO channel_guidelines (guild_id, channel_id, guidelines)
                        VALUES (?, ?, ?)
                        ON CONFLICT(guild_id, channel_id) DO UPDATE SET
                            guidelines = excluded.guidelines
                    """, (guild_id.to_int(), channel_id.to_int(), guidelines))
                    await db.commit()
                    logger.debug(
                        "[GUILD SETTINGS MANAGER] Persisted channel guidelines for guild %s, channel %s to database",
                        guild_id,
                        channel_id
                    )
                    return True
            except Exception:
                logger.exception(
                    "[GUILD SETTINGS MANAGER] Failed to persist channel guidelines for guild %s, channel %s to database",
                    guild_id,
                    channel_id
                )
                return False

    async def load_from_disk(self) -> bool:
        """Load persisted guild settings from database into memory."""
        try:
            async with get_db().get_connection() as db:
                # Load guild settings
                async with db.execute("""
                    SELECT 
                        guild_id, ai_enabled, rules,
                        auto_warn_enabled, auto_delete_enabled,
                        auto_timeout_enabled, auto_kick_enabled, auto_ban_enabled,
                        auto_review_enabled
                    FROM guild_settings
                """) as cursor:
                    rows = await cursor.fetchall()
                    
                self.guilds.clear()
                for row in rows:
                    guild_id_int = row[0]
                    guild_id = GuildID.from_int(guild_id_int)
                    
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
                    )

                    self.guilds[guild_id] = settings
                
                # Load moderator roles for all guilds
                async with db.execute("SELECT guild_id, role_id FROM guild_moderator_roles ORDER BY guild_id, role_id") as cursor:
                    role_rows = await cursor.fetchall()
                
                for row in role_rows:
                    guild_id_int = row[0]
                    role_id = row[1]
                    guild_id = GuildID.from_int(guild_id_int)
                    if guild_id in self.guilds:
                        self.guilds[guild_id].moderator_role_ids.append(role_id)
                
                # Load review channels for all guilds
                async with db.execute("SELECT guild_id, channel_id FROM guild_review_channels ORDER BY guild_id, channel_id") as cursor:
                    channel_rows = await cursor.fetchall()
                
                for row in channel_rows:
                    guild_id_int = row[0]
                    channel_id_int = row[1]
                    guild_id = GuildID.from_int(guild_id_int)
                    if guild_id in self.guilds:
                        self.guilds[guild_id].review_channel_ids.append(ChannelID.from_int(channel_id_int))
                
                # Load channel guidelines
                async with db.execute("SELECT guild_id, channel_id, guidelines FROM channel_guidelines") as cursor:
                    guidelines_rows = await cursor.fetchall()
                
                self.channel_guidelines.clear()
                for row in guidelines_rows:
                    guild_id_int = row[0]
                    channel_id_int = row[1]
                    guidelines = row[2]
                    
                    guild_id = GuildID.from_int(guild_id_int)
                    channel_id = ChannelID.from_int(channel_id_int)
                    
                    if guild_id not in self.channel_guidelines:
                        self.channel_guidelines[guild_id] = {}
                    self.channel_guidelines[guild_id][channel_id] = guidelines
                
                if rows:
                    logger.info("[GUILD SETTINGS MANAGER] Loaded %d guild settings from database", len(list(rows)))
                if guidelines_rows:
                    logger.info("[GUILD SETTINGS MANAGER] Loaded %d channel guidelines from database", len(list(guidelines_rows)))
                
                return bool(rows or guidelines_rows)
        except Exception:
            logger.exception("[GUILD SETTINGS MANAGER] Failed to load guild settings from database")
            return False

    async def persist_guild(self, guild_id: GuildID) -> bool:
        """
        Persist a single guild's settings to database asynchronously.

        Return whether the write was successful or not.

        This version performs only asynchronous writes. Callers must invoke
        and await this coroutine from an active event loop.
        """
        return await self._persist_guild_async(guild_id)


# Global guild settings manager instance
guild_settings_manager = GuildSettingsManager()