"""
Persistent per-guild configuration storage for the moderation bot.

Provides a simplified API for managing guild settings:
- get_settings(guild_id) -> GuildSettings: Retrieve settings (creates default if missing)
- update(guild_id, **kwargs): Update fields and auto-persist
- is_action_allowed/set_action_allowed: Action-type specific helpers
- save(guild_id, settings): Explicit persist trigger

Database operations are delegated to GuildSettingsDB.
"""
import asyncio
from typing import Any, Dict, Set

from modcord.datatypes.discord_datatypes import GuildID, ChannelID
from modcord.datatypes.action_datatypes import ActionType
from modcord.datatypes.guild_settings import GuildSettings, ACTION_FLAG_FIELDS
from modcord.settings.guild_settings_db import guild_settings_db
from modcord.util.logger import get_logger

logger = get_logger("guild_settings_manager")


class GuildSettingsManager:
    """
    Manager for persistent per-guild settings.

    Provides a clean API:
    - get_settings(guild_id): Retrieve settings object
    - update(guild_id, **kwargs): Update fields and auto-persist
    - is_action_allowed/set_action_allowed: ActionType helpers
    - save(guild_id, settings): Explicit persist
    """

    def __init__(self):
        """Instantiate caches and persistence helpers."""
        self._rules_cache: Dict[GuildID, str] = {}
        self._guidelines_cache: Dict[GuildID, Dict[ChannelID, str]] = {}
        self._persist_lock = asyncio.Lock()
        self._active_persists: Set[asyncio.Task] = set()
        self._db_initialized = False

        logger.info("[GUILD SETTINGS MANAGER] Initialized")


    async def async_init(self) -> None:
        """Initialize the database and load settings from disk."""
        if not self._db_initialized:
            await guild_settings_db.initialize()
            loaded_guilds = await guild_settings_db.load_all_guild_settings()
            
            # Populate only rules and guidelines caches
            for guild_id, settings in loaded_guilds.items():
                if settings.rules:
                    self._rules_cache[guild_id] = settings.rules
                if settings.channel_guidelines:
                    self._guidelines_cache[guild_id] = settings.channel_guidelines.copy()
            
            self._db_initialized = True
            logger.info("[GUILD SETTINGS MANAGER] Database initialized and caches loaded")


    # ========== Core API ==========

    async def get_settings(self, guild_id: GuildID) -> GuildSettings:
        """
        Retrieve settings for a guild, creating defaults if missing.

        Args:
            guild_id: The guild ID to fetch settings for.

        Returns:
            GuildSettings instance for the guild.
        """
        if not isinstance(guild_id, GuildID):
            guild_id = GuildID(guild_id)
        
        settings = await guild_settings_db.fetch_guild_settings(guild_id)
        if settings is None:
            settings = GuildSettings(guild_id=guild_id)
        
        # Overwrite with cached values
        if guild_id in self._rules_cache:
            settings.rules = self._rules_cache[guild_id]
        
        if guild_id in self._guidelines_cache:
            settings.channel_guidelines = self._guidelines_cache[guild_id].copy()
            
        return settings

    def get_cached_rules(self, guild_id: GuildID) -> str:
        """Get cached rules for a guild."""
        if not isinstance(guild_id, GuildID):
            guild_id = GuildID(guild_id)
        return self._rules_cache.get(guild_id, "")

    def get_cached_guidelines(self, guild_id: GuildID) -> Dict[ChannelID, str]:
        """Get cached guidelines for a guild."""
        if not isinstance(guild_id, GuildID):
            guild_id = GuildID(guild_id)
        return self._guidelines_cache.get(guild_id, {}).copy()

    async def update(self, guild_id: GuildID, **kwargs: Any) -> GuildSettings:
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
        
        settings = await self.get_settings(guild_id)
        
        for field_name, value in kwargs.items():
            if hasattr(settings, field_name):
                setattr(settings, field_name, value)
                
                # Update caches if necessary
                if field_name == "rules":
                    self._rules_cache[guild_id] = value
                elif field_name == "channel_guidelines":
                    self._guidelines_cache[guild_id] = value.copy()
            else:
                logger.warning(
                    "[GUILD SETTINGS MANAGER] Unknown field %s for guild %s",
                    field_name, guild_id.to_int()
                )
        
        await self.save(guild_id, settings)
        return settings

    async def save(self, guild_id: GuildID, settings: GuildSettings) -> None:
        """
        Persist guild settings to database.

        Args:
            guild_id: The guild ID to persist.
            settings: The settings object to persist.
        """
        if not isinstance(guild_id, GuildID):
            guild_id = GuildID(guild_id)
        
        try:
            success = await self._persist_guild(guild_id, settings)
            if not success:
                logger.error(
                    "[GUILD SETTINGS MANAGER] Failed to persist guild %s",
                    guild_id.to_int()
                )
        except Exception:
            logger.exception("Error persisting guild %s", guild_id.to_int())


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
        if not isinstance(guild_id, GuildID):
            guild_id = GuildID(guild_id)
           
        # Remove from memory cache
        if guild_id in self._rules_cache:
            del self._rules_cache[guild_id]
        if guild_id in self._guidelines_cache:
            del self._guidelines_cache[guild_id]
            
        logger.debug(f"[GUILD SETTINGS MANAGER] Removed guild {guild_id.to_int()} from memory cache")
        
        # Delete from database
        return await guild_settings_db.delete_guild_data(guild_id)



    # ========== Action Type Helpers ==========

    async def is_action_allowed(self, guild_id: GuildID, action: ActionType) -> bool:
        """
        Check if a specific action type is enabled for the guild.

        Args:
            guild_id: The guild ID.
            action: The ActionType to check.

        Returns:
            True if the action is allowed, False otherwise.
        """
        if not isinstance(guild_id, GuildID):
            guild_id = GuildID(guild_id)

        settings = await self.get_settings(guild_id)
        field_name = ACTION_FLAG_FIELDS.get(action)
        if field_name is None:
            return True
        return bool(getattr(settings, field_name, True))


    async def set_action_allowed(self, guild_id: GuildID, action: ActionType, enabled: bool) -> bool:
        """
        Enable or disable an action type for the guild and auto-persist.

        Args:
            guild_id: The guild ID.
            action: The ActionType to toggle.
            enabled: Whether to enable or disable.

        Returns:
            True if successful, False if action type is unsupported.
        """
        if not isinstance(guild_id, GuildID):
            guild_id = GuildID(guild_id)

        field_name = ACTION_FLAG_FIELDS.get(action)
        if field_name is None:
            logger.warning(
                "[GUILD SETTINGS MANAGER] Unsupported action %s for guild %s",
                action, guild_id
            )
            return False

        await self.update(guild_id, **{field_name: bool(enabled)})
        return True

    # ========== Lifecycle ==========

    async def shutdown(self) -> None:
        """Await any pending persistence tasks during shutdown."""
        await asyncio.gather(*self._active_persists, return_exceptions=True)
        self._active_persists.clear()
        logger.info("[GUILD SETTINGS MANAGER] Shutdown complete")


    # ========== Private Methods ==========

    async def _persist_guild(self, guild_id: GuildID, settings: GuildSettings) -> bool:
        """Persist a single guild's settings to database."""
        return await guild_settings_db.save_guild_settings(guild_id, settings)


# Global instance
guild_settings_manager = GuildSettingsManager()