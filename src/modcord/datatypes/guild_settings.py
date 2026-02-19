from dataclasses import dataclass, field
from typing import Dict, Optional

from modcord.datatypes.action_datatypes import ActionType
from modcord.datatypes.discord_datatypes import ChannelID, GuildID

ACTION_FLAG_FIELDS: Dict[ActionType, str] = {
    ActionType.WARN: "auto_warn_enabled",
    ActionType.DELETE: "auto_delete_enabled",
    ActionType.TIMEOUT: "auto_timeout_enabled",
    ActionType.KICK: "auto_kick_enabled",
    ActionType.BAN: "auto_ban_enabled",
}


@dataclass
class GuildSettings:
    """Persistent per-guild configuration values with controlled flag updates."""

    guild_id: GuildID
    ai_enabled: bool = True
    rules: str = ""

    # Private backing fields for action flags
    _auto_warn_enabled: bool = True
    _auto_delete_enabled: bool = True
    _auto_timeout_enabled: bool = True
    _auto_kick_enabled: bool = True
    _auto_ban_enabled: bool = True

    # collections
    channel_guidelines: Dict[ChannelID, str] = field(default_factory=dict)

    # Mod-log channel for posting action embeds
    mod_log_channel_id: Optional[ChannelID] = None

    # -------------------------
    # Properties (getters/setters)
    # -------------------------

    @property
    def auto_warn_enabled(self) -> bool:
        return self._auto_warn_enabled

    @auto_warn_enabled.setter
    def auto_warn_enabled(self, value: bool) -> None:
        self._auto_warn_enabled = value

    @property
    def auto_delete_enabled(self) -> bool:
        return self._auto_delete_enabled

    @auto_delete_enabled.setter
    def auto_delete_enabled(self, value: bool) -> None:
        self._auto_delete_enabled = value

    @property
    def auto_timeout_enabled(self) -> bool:
        return self._auto_timeout_enabled

    @auto_timeout_enabled.setter
    def auto_timeout_enabled(self, value: bool) -> None:
        self._auto_timeout_enabled = value

    @property
    def auto_kick_enabled(self) -> bool:
        return self._auto_kick_enabled

    @auto_kick_enabled.setter
    def auto_kick_enabled(self, value: bool) -> None:
        self._auto_kick_enabled = value

    @property
    def auto_ban_enabled(self) -> bool:
        return self._auto_ban_enabled

    @auto_ban_enabled.setter
    def auto_ban_enabled(self, value: bool) -> None:
        self._auto_ban_enabled = value