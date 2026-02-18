"""
Action types and data structures for moderation actions.

This module defines the ActionType enum and ActionData dataclass used to represent
moderation actions throughout the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple

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


class Actions:
    @staticmethod
    def warn(
        guild_id: GuildID,
        channel_id: ChannelID,
        user_id: UserID,
        reason: str,
    ) -> ActionData:

        return ActionData(
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
            action=ActionType.WARN,
            reason=reason,
        )


    @staticmethod
    def timeout(
        guild_id: GuildID,
        channel_id: ChannelID,
        user_id: UserID,
        duration_minutes: int,
        reason: str,
    ) -> ActionData:

        return ActionData(
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
            action=ActionType.TIMEOUT,
            reason=reason,
            timeout_duration=duration_minutes,
        )

    @staticmethod
    def kick(
        guild_id: GuildID,
        channel_id: ChannelID,
        user_id: UserID,
        reason: str,
    ) -> ActionData:

        return ActionData(
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
            action=ActionType.KICK,
            reason=reason,
        )
    
    @staticmethod
    def ban(
        guild_id: GuildID,
        channel_id: ChannelID,
        user_id: UserID,
        duration_minutes: int,
        reason: str,
    ) -> ActionData:

        return ActionData(
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
            action=ActionType.BAN,
            reason=reason,
            ban_duration=duration_minutes,
        )

    @staticmethod
    def unban(
        guild_id: GuildID,
        channel_id: ChannelID,
        user_id: UserID,
        reason: str,
    ) -> ActionData:

        return ActionData(
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
            action=ActionType.UNBAN,
            reason=reason,
        )
    

    @staticmethod
    def delete(
        guild_id: GuildID,
        channel_id: ChannelID,
        user_id: UserID,
        message_ids_to_delete: Tuple[MessageID, ...],
        reason: str,
    ) -> ActionData:

        return ActionData(
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
            action=ActionType.DELETE,
            message_ids_to_delete=message_ids_to_delete,
            reason=reason,
        )
    

    @staticmethod
    def review(
        guild_id: GuildID,
        channel_id: ChannelID,
        user_id: UserID,
        reason: str,
    ) -> ActionData:

        return ActionData(
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
            action=ActionType.REVIEW,
            reason=reason,
        )


@dataclass(slots=True, frozen=True)
class ActionData:

    guild_id: GuildID
    channel_id: ChannelID
    user_id: UserID
    action: ActionType
    reason: str

    timeout_duration: Optional[int] = None
    ban_duration: Optional[int] = None

    message_ids_to_delete: Tuple[MessageID, ...] = field(default_factory=tuple)