"""Utility types for moderation actions and message payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, List, Optional, Sequence, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import only for type checkers
    import discord


class ActionType(Enum):
    """Enumeration of supported moderation actions."""

    BAN = "ban"
    UNBAN = "unban"
    KICK = "kick"
    WARN = "warn"
    DELETE = "delete"
    TIMEOUT = "timeout"
    NULL = "null"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


@dataclass(slots=True)
class ActionData:
    """Normalized moderation action payload.

    Attributes:
        user_id: Snowflake of target user, stored as string for JSON parity.
        action: Moderation action to execute.
        reason: Human-readable explanation for auditing/logging.
        message_ids: Related message IDs to operate on (deleted, audited, etc.).
        timeout_duration: Optional timeout duration in seconds (``None`` to use default).
        ban_duration: Optional ban duration in seconds (``None``/``0`` -> permanent).
    """

    user_id: str
    action: ActionType
    reason: str
    message_ids: List[str] = field(default_factory=list)
    timeout_duration: Optional[int] = None
    ban_duration: Optional[int] = None

    def add_message_ids(self, *message_ids: str) -> None:
        """Append sanitized message IDs, preserving order and ignoring duplicates."""

        for raw_mid in message_ids:
            mid = str(raw_mid).strip()
            if not mid:
                continue
            if mid not in self.message_ids:
                self.message_ids.append(mid)

    def replace_message_ids(self, message_ids: Iterable[str]) -> None:
        """Overwrite the message IDs list with sanitized values."""

        self.message_ids.clear()
        self.add_message_ids(*message_ids)

    def to_wire_dict(self) -> dict:
        """Serialize to a plain dictionary for logging or JSON emission."""

        return {
            "user_id": self.user_id,
            "action": self.action.value,
            "reason": self.reason,
            "message_ids": list(self.message_ids),
            "timeout_duration": self.timeout_duration,
            "ban_duration": self.ban_duration,
        }


@dataclass(slots=True)
class ModerationMessage:
    """Normalized representation of a Discord message for moderation decisions."""

    message_id: str
    user_id: str
    username: str
    content: str
    timestamp: str
    guild_id: Optional[int]
    channel_id: Optional[int]
    role: str = "user"
    image_summary: Optional[str] = None
    discord_message: "discord.Message | None" = None

    def to_model_payload(self) -> dict:
        """Convert to the dictionary structure expected by the AI model."""

        return {
            "message_id": self.message_id,
            "user_id": self.user_id,
            "username": self.username,
            "content": self.content,
            "timestamp": self.timestamp,
            "image_summary": self.image_summary,
        }

    def to_history_payload(self) -> dict:
        """Convert to the history message shape used by single-message moderation."""

        return {
            "role": self.role,
            "user_id": self.user_id,
            "username": self.username,
            "timestamp": self.timestamp,
            "content": self.content,
        }


@dataclass(slots=True)
class ModerationBatch:
    """Container describing a batch of messages awaiting moderation."""

    channel_id: int
    messages: List[ModerationMessage] = field(default_factory=list)

    def add_message(self, message: ModerationMessage) -> None:
        self.messages.append(message)

    def extend(self, messages: Sequence[ModerationMessage]) -> None:
        self.messages.extend(messages)

    def is_empty(self) -> bool:
        return not self.messages

    def to_model_payload(self) -> List[dict]:
        return [msg.to_model_payload() for msg in self.messages]