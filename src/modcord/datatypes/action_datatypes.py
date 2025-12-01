"""
Action types and data structures for moderation actions.

This module defines the ActionType enum and ActionData dataclass used to represent
moderation actions throughout the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List

from modcord.datatypes.discord_datatypes import ChannelID, UserID, GuildID, MessageID


class ActionType(Enum):
    """Enumeration of supported moderation actions."""

    BAN = "ban"
    UNBAN = "unban"
    KICK = "kick"
    WARN = "warn"
    DELETE = "delete"
    TIMEOUT = "timeout"
    REVIEW = "review"
    NULL = "null"

    def __str__(self) -> str:
        return self.value


@dataclass(slots=True)
class ActionData:
    """Data structure representing a moderation action.
    
    Attributes:
        guild_id: ID of the guild where the action should be performed
        user_id: ID of the user the action is taken against
        action: Type of action to perform
        reason: Reason for the action
        timeout_duration: Duration of timeout in minutes (0 if not applicable, -1 for max)
        ban_duration: Duration of ban in minutes (0 for permanent, -1 for max)
        message_ids: List of message IDs to delete (for delete actions)
    """
    guild_id: GuildID
    channel_id: ChannelID
    user_id: UserID
    action: ActionType
    reason: str
    timeout_duration: int = 0
    ban_duration: int = 0
    message_ids_to_delete: List[MessageID] = field(default_factory=list)