"""
Persistent per-guild configuration storage for the moderation bot.

Provides a simplified API for managing guild settings:
- get_settings(guild_id) -> GuildSettings: Retrieve settings (creates default if missing)
- update(guild_id, **kwargs): Update fields and auto-persist
- is_action_allowed/set_action_allowed: Action-type specific helpers
- save(guild_id, settings): Explicit persist trigger

All reads go directly to the database — there is no in-memory cache.
This keeps state simple and consistent at the cost of a DB round-trip
per read, which is acceptable given SQLite's WAL read performance and
the 256 MB page cache configured on the connection.
"""
from typing import Any, Dict

from modcord.datatypes.action_datatypes import ActionType
from modcord.datatypes.discord_datatypes import GuildID, ChannelID
from modcord.datatypes.guild_settings import GuildSettings, ACTION_FLAG_FIELDS
from modcord.services.guild_settings_service import guild_settings_service
from modcord.util.logger import get_logger

logger = get_logger("guild_settings_manager")


class GuildSettingsManager:
    """
    Manager for persistent per-guild settings.

    No in-memory cache — every read hits the database directly.
    SQLite's WAL mode and page cache make this fast enough in practice.

    Public API:
    - get_settings(guild_id): Retrieve settings object (creates defaults if missing)
    - get_rules(guild_id): Fetch just the rules string
    - get_guidelines(guild_id): Fetch just the channel guidelines map
    - update(guild_id, **kwargs): Update fields and auto-persist
    - is_action_allowed(guild_id, action): DB-backed action flag check
    - set_action_allowed(guild_id, action, enabled): Toggle an action flag
    - save(guild_id, settings): Explicit persist
    - delete(guild_id): Remove all data for a guild
    """

    def __init__(self) -> None:
        self._db_initialized = False
        logger.info("[GUILD SETTINGS MANAGER] Initialized")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_init(self) -> None:
        """Initialize the database service."""
        if not self._db_initialized:
            await guild_settings_service.initialize()
            self._db_initialized = True
            logger.info("[GUILD SETTINGS MANAGER] Database initialized")

    async def shutdown(self) -> None:
        """No-op — nothing to flush without a cache."""
        logger.info("[GUILD SETTINGS MANAGER] Shutdown complete")

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    async def get_settings(self, guild_id: GuildID) -> GuildSettings:
        """
        Retrieve settings for a guild, creating defaults if missing.

        Always reads from the database.

        Args:
            guild_id: The guild ID to fetch settings for.

        Returns:
            GuildSettings instance for the guild.
        """
        if not isinstance(guild_id, GuildID):
            guild_id = GuildID(guild_id)

        settings = await guild_settings_service.fetch(guild_id)
        if settings is None:
            settings = GuildSettings(guild_id=guild_id)

        return settings

    async def get_rules(self, guild_id: GuildID) -> str:
        """
        Fetch just the rules string for a guild directly from the DB.

        Args:
            guild_id: The guild ID.

        Returns:
            The rules string, or an empty string if none are set.
        """
        settings = await self.get_settings(guild_id)
        return settings.rules

    async def get_guidelines(self, guild_id: GuildID) -> Dict[ChannelID, str]:
        """
        Fetch just the channel guidelines map for a guild directly from the DB.

        Args:
            guild_id: The guild ID.

        Returns:
            Dict mapping ChannelID to guideline text.
        """
        settings = await self.get_settings(guild_id)
        return settings.channel_guidelines.copy() if settings.channel_guidelines else {}

    async def update(self, guild_id: GuildID, **kwargs: Any) -> GuildSettings:
        """
        Update settings fields and auto-persist.

        Reads current settings from the DB, applies the given fields,
        then writes back immediately.

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
            else:
                logger.warning(
                    "[GUILD SETTINGS MANAGER] Unknown field %s for guild %s",
                    field_name, int(guild_id)
                )

        await self.save(guild_id, settings)
        return settings

    async def save(self, guild_id: GuildID, settings: GuildSettings) -> None:
        """
        Persist guild settings to the database.

        Args:
            guild_id: The guild ID to persist.
            settings: The settings object to persist.
        """
        if not isinstance(guild_id, GuildID):
            guild_id = GuildID(guild_id)

        success = await guild_settings_service.save(guild_id, settings)
        if not success:
            logger.error(
                "[GUILD SETTINGS MANAGER] Failed to persist guild %s",
                int(guild_id)
            )

    async def delete(self, guild_id: GuildID) -> bool:
        """
        Delete all data for a guild from the database.

        Args:
            guild_id: The guild ID to delete.

        Returns:
            True if successful, False otherwise.
        """
        if not isinstance(guild_id, GuildID):
            guild_id = GuildID(guild_id)

        return await guild_settings_service.delete(guild_id)

    # ------------------------------------------------------------------
    # Action Type Helpers
    # ------------------------------------------------------------------

    async def is_action_allowed(self, guild_id: GuildID, action: ActionType) -> bool:
        """
        Check if a specific action type is enabled for a guild.

        Always reads from the database for an accurate result.

        Args:
            guild_id: The guild ID.
            action: The ActionType to check.

        Returns:
            True if the action is allowed, False otherwise.
            Defaults to True if the action flag is not mapped.
        """
        field_name = ACTION_FLAG_FIELDS.get(action)
        if field_name is None:
            logger.warning(
                "[GUILD SETTINGS MANAGER] Unsupported action %s for guild %s — defaulting to allowed",
                action, guild_id
            )
            return True

        settings = await self.get_settings(guild_id)
        return bool(getattr(settings, field_name, True))

    async def set_action_allowed(self, guild_id: GuildID, action: ActionType, enabled: bool) -> bool:
        """
        Enable or disable an action type for the guild and auto-persist.

        Args:
            guild_id: The guild ID.
            action: The ActionType to toggle.
            enabled: Whether to enable or disable.

        Returns:
            True if successful, False if the action type is unsupported.
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


# Global instance
guild_settings_manager = GuildSettingsManager()