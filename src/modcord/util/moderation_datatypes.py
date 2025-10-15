"""Utility types for moderation actions and message payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Optional, Sequence
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

    def __str__(self) -> str:
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
        """Append one or more message identifiers to the action payload.

        Parameters
        ----------
        *message_ids:
            Discord message identifiers associated with the moderation action.
        """

        for raw_mid in message_ids:
            mid = str(raw_mid).strip()
            if not mid:
                continue
            if mid not in self.message_ids:
                self.message_ids.append(mid)

    def replace_message_ids(self, message_ids: Iterable[str]) -> None:
        """Replace the tracked message identifiers with the provided iterable.

        Parameters
        ----------
        message_ids:
            Iterable of message identifiers that should overwrite the current list.
        """

        self.message_ids.clear()
        self.add_message_ids(*message_ids)

    def to_wire_dict(self) -> dict:
        """Return a JSON-serializable dictionary representing this action."""

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
    """Normalized message data used to provide context to the moderation engine."""

    message_id: str
    user_id: str
    username: str
    content: str
    timestamp: str  # ISO 8601 string, e.g. '2025-10-09T12:34:56Z'
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
            "role": self.role,
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
    """Container for batched moderation messages plus optional historical context."""

    channel_id: int
    messages: List[ModerationMessage] = field(default_factory=list)
    history: List[ModerationMessage] = field(default_factory=list)

    def add_message(self, message: ModerationMessage) -> None:
        self.messages.append(message)

    def extend(self, messages: Sequence[ModerationMessage]) -> None:
        self.messages.extend(messages)

    def set_history(self, history: Sequence[ModerationMessage]) -> None:
        self.history = list(history)

    def is_empty(self) -> bool:
        return not self.messages

    def to_model_payload(self) -> List[dict]:
        return [msg.to_model_payload() for msg in self.messages]

    def history_to_model_payload(self) -> List[dict]:
        return [msg.to_model_payload() for msg in self.history]

    def to_user_payload(self) -> List[dict]:
        """Group batch messages by user and return a summary payload.

        The structure is optimized for model consumption: each user entry
        contains metadata plus the ordered list of their messages in this
        batch, enabling the model to reason about per-user context without
        re-parsing the flat message stream.
        """

        grouped: Dict[str, dict] = {}
        for index, message in enumerate(self.messages):
            user_id = str(message.user_id)
            if user_id not in grouped:
                grouped[user_id] = {
                    "user_id": user_id,
                    "username": message.username,
                    "message_count": 0,
                    "first_message_timestamp": message.timestamp,
                    "latest_message_timestamp": message.timestamp,
                    "messages": [],
                    "__first_index": index,
                }

            entry = grouped[user_id]
            entry_messages = entry["messages"]
            entry_messages.append(
                {
                    "message_id": message.message_id,
                    "timestamp": message.timestamp,
                    "content": message.content,
                    "image_summary": message.image_summary,
                    "order_index": index,
                    "role": message.role,
                }
            )
            entry["message_count"] += 1
            # Update timestamps for clarity in prompts
            if message.timestamp < entry["first_message_timestamp"]:
                entry["first_message_timestamp"] = message.timestamp
            if message.timestamp > entry["latest_message_timestamp"]:
                entry["latest_message_timestamp"] = message.timestamp

        # Sort messages per user by original order to guarantee determinism
        for entry in grouped.values():
            entry["messages"].sort(key=lambda item: item["order_index"])
            for item in entry["messages"]:
                item.pop("order_index", None)

        # Return users in deterministic order based on first appearance
        ordered_users = []
        for entry in grouped.values():
            ordered_users.append(entry)

        ordered_users.sort(
            key=lambda entry: (
                entry.get("first_message_timestamp") or "",
                entry.get("__first_index", 0),
                entry["user_id"],
            )
        )

        for entry in ordered_users:
            entry.pop("__first_index", None)

        return ordered_users