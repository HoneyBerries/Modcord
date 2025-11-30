"""
Persistent per-guild configuration storage for the moderation bot.

Database schema:
- guild_settings table with columns: guild_id, ai_enabled, rules, auto_*_enabled flags
- channel_guidelines table with columns: guild_id, channel_id, guidelines
"""
from typing import Dict, List
from dataclasses import dataclass, field
from modcord.datatypes.discord_datatypes import ChannelID, GuildID
from modcord.datatypes.action_datatypes import ActionType


# Maps ActionType enum to the corresponding boolean field name on GuildSettings
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
    """Persistent per-guild configuration values."""

    guild_id: GuildID
    ai_enabled: bool = False
    rules: str = ""
    auto_warn_enabled: bool = False
    auto_delete_enabled: bool = False
    auto_timeout_enabled: bool = False
    auto_kick_enabled: bool = False
    auto_ban_enabled: bool = False
    auto_review_enabled: bool = False
    moderator_role_ids: List[int] = field(default_factory=list)
    review_channel_ids: List[ChannelID] = field(default_factory=list)
    channel_guidelines: Dict[ChannelID, str] = field(default_factory=dict)