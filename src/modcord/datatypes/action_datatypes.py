"""
Action types and data structures for moderation actions.

This module defines the ActionType enum, ChannelDeleteSpec, and ActionData
dataclass used to represent moderation actions throughout the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Tuple

from modcord.datatypes.discord_datatypes import ChannelID, UserID, GuildID, MessageID


class ActionType(Enum):
    """Enumeration of supported moderation actions."""

    BAN = "ban"
    UNBAN = "unban"
    KICK = "kick"
    WARN = "warn"
    DELETE = "delete"
    TIMEOUT = "timeout"
    NULL = "null"

    def __str__(self) -> str:
        return self.value


@dataclass(slots=True, frozen=True)
class ChannelDeleteSpec:
    """Messages to delete from a specific channel."""
    channel_id: ChannelID
    message_ids: Tuple[MessageID, ...] = ()


class Actions:
    @staticmethod
    def warn(
        guild_id: GuildID,
        user_id: UserID,
        reason: str,
    ) -> ActionData:
        return ActionData(
            guild_id=guild_id,
            user_id=user_id,
            action=ActionType.WARN,
            reason=reason,
            ban_duration=0,
            timeout_duration=0,
        )

    @staticmethod
    def timeout(
        guild_id: GuildID,
        user_id: UserID,
        duration_seconds: int,
        reason: str,
    ) -> ActionData:
        return ActionData(
            guild_id=guild_id,
            user_id=user_id,
            action=ActionType.TIMEOUT,
            reason=reason,
            timeout_duration=duration_seconds,
            ban_duration=0,
        )

    @staticmethod
    def kick(
        guild_id: GuildID,
        user_id: UserID,
        reason: str,
    ) -> ActionData:
        return ActionData(
            guild_id=guild_id,
            user_id=user_id,
            action=ActionType.KICK,
            reason=reason,
            ban_duration=0,
            timeout_duration=0,
        )

    @staticmethod
    def ban(
        guild_id: GuildID,
        user_id: UserID,
        duration_seconds: int,
        reason: str,
    ) -> ActionData:
        return ActionData(
            guild_id=guild_id,
            user_id=user_id,
            action=ActionType.BAN,
            reason=reason,
            ban_duration=duration_seconds,
            timeout_duration=0,
        )

    @staticmethod
    def unban(
        guild_id: GuildID,
        user_id: UserID,
        reason: str,
    ) -> ActionData:
        return ActionData(
            guild_id=guild_id,
            user_id=user_id,
            action=ActionType.UNBAN,
            reason=reason,
            ban_duration=0,
            timeout_duration=0,
        )

    @staticmethod
    def delete(
        guild_id: GuildID,
        user_id: UserID,
        channel_deletions: Tuple[ChannelDeleteSpec, ...],
        reason: str,
    ) -> ActionData:
        return ActionData(
            guild_id=guild_id,
            user_id=user_id,
            action=ActionType.DELETE,
            channel_deletions=channel_deletions,
            reason=reason,
            ban_duration=0,
            timeout_duration=0,
        )


@dataclass(slots=True, frozen=True)
class ActionData:
    """A moderation action to apply to a user.

    channel_deletions maps each channel to the specific message IDs
    that should be deleted in that channel.

    timeout_duration and ban_duration are ALWAYS in SECONDS — never minutes or hours.
    """

    guild_id: GuildID
    user_id: UserID
    action: ActionType
    reason: str

    timeout_duration: int
    ban_duration: int

    channel_deletions: Tuple[ChannelDeleteSpec, ...] = field(default_factory=tuple)

    @property
    def all_message_ids(self) -> Tuple[MessageID, ...]:
        """Flat view of every message ID across all channel deletions."""
        return tuple(mid for spec in self.channel_deletions for mid in spec.message_ids)