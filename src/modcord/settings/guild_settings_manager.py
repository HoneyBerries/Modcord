"""
Persistent per-guild configuration storage for the moderation bot.

Provides a simplified API for managing guild settings:
- get(guild_id) -> GuildSettings: Retrieve settings (creates default if missing)
- update(guild_id, **kwargs): Update fields and auto-persist
- is_action_allowed/set_action_allowed: Action-type specific helpers
- save(guild_id): Explicit persist trigger

Database operations are delegated to GuildSettingsDB.
"""
import asyncio
from typing import Any, Dict, Set

from modcord.datatypes.discord_datatypes import GuildID
from modcord.datatypes.action_datatypes import ActionType
from modcord.datatypes.guild_settings import GuildSettings, ACTION_FLAG_FIELDS
from modcord.settings.guild_settings_db import GuildSettingsDB
from modcord.util.logger import get_logger

logger = get_logger("guild_settings_manager")

guild_settings_db = GuildSettingsDB()


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
            await guild_settings_db.initialize()
            loaded_guilds = await guild_settings_db.load_all_guild_settings()
            self._guilds.update(loaded_guilds)
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


    async def delete(self, guild_id: GuildID) -> bool:
        """Delete all data for a guild from memory and database.
        
        This removes:
        - Guild settings
        - Moderator roles
        - Review channels
        - Channel guidelines
        - Moderation action history (if applicable)
        
        Args:
            guild_id: The guild ID to delete.
            
        Returns:
            True if successful, False otherwise.
        """           
        # Remove from memory cache
        if guild_id in self._guilds:
            del self._guilds[guild_id]
            logger.debug(f"[GUILD SETTINGS MANAGER] Removed guild {guild_id.to_int()} from memory cache")
        
        # Delete from database
        return await guild_settings_db.delete_guild_data(guild_id)



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
        await asyncio.gather(*self._active_persists, return_exceptions=True)
        self._active_persists.clear()
        logger.info("[GUILD SETTINGS MANAGER] Shutdown complete")


    # ========== Private Methods ==========

    async def _persist_guild(self, guild_id: GuildID) -> bool:
        """Persist a single guild's settings to database."""
        settings = self._guilds.get(guild_id)
        if settings is None:
            logger.warning(
                "[GUILD SETTINGS MANAGER] Cannot persist guild %s: not in cache",
                guild_id.to_int()
            )
            return False

        return await guild_settings_db.save_guild_settings(guild_id, settings)


# Global instance
guild_settings_manager = GuildSettingsManager()