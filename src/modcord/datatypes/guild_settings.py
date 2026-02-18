from dataclasses import dataclass, field
from typing import Dict, Set
from modcord.datatypes.discord_datatypes import ChannelID, GuildID
from modcord.datatypes.action_datatypes import ActionType

ACTION_FLAG_FIELDS: Dict[ActionType, str] = {
    ActionType.WARN: "auto_warn_enabled",
    ActionType.DELETE: "auto_delete_enabled",
    ActionType.TIMEOUT: "auto_timeout_enabled",
    ActionType.KICK: "auto_kick_enabled",
    ActionType.BAN: "auto_ban_enabled",
    ActionType.REVIEW: "auto_review_enabled",
}


@dataclass(slots=True)
class GuildSettings:
    """Persistent per-guild configuration values with controlled flag updates."""

    guild_id: GuildID
    ai_enabled: bool = True
    rules: str = ""

    # private flags
    _auto_warn_enabled: bool = True
    _auto_delete_enabled: bool = True
    _auto_timeout_enabled: bool = True
    _auto_kick_enabled: bool = True
    _auto_ban_enabled: bool = True
    _auto_review_enabled: bool = True

    # collections
    moderator_role_ids: Set[int] = field(default_factory=set)
    review_channel_ids: Set[ChannelID] = field(default_factory=set)
    channel_guidelines: Dict[ChannelID, str] = field(default_factory=dict)

    # -------------------------
    # Flag access methods
    # -------------------------

    def is_auto_enabled(self, action: ActionType) -> bool:
        """Check if auto-action is enabled for a given ActionType."""
        field = ACTION_FLAG_FIELDS.get(action)
        if field is None:
            return False
        return getattr(self, f"_{field}")

    def set_auto_enabled(self, action: ActionType, enabled: bool) -> None:
        """Enable or disable auto-action for a given ActionType."""
        field = ACTION_FLAG_FIELDS.get(action)
        if field is None:
            raise ValueError(f"No auto-flag for action {action}")
        setattr(self, f"_{field}", enabled)