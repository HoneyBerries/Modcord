"""Utility types for moderation actions and message payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Iterable, List, Optional, Sequence
import discord
from modcord.util.logger import get_logger

logger = get_logger("moderation_datatypes")


def humanize_timestamp(value: str) -> str:
    """Return a human-readable timestamp (YYYY-MM-DD HH:MM:SS) in UTC."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    dt = dt.astimezone(timezone.utc)
    
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


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
    image_summary: Optional[str] = None
    discord_message: "discord.Message | None" = None

    def to_model_payload(self) -> dict:
        """Convert to the dictionary structure expected by the AI model."""

        timestamp_value = humanize_timestamp(self.timestamp)

        return {
            "message_id": self.message_id,
            "user_id": self.user_id,
            "username": self.username,
            "content": self.content,
            "timestamp": timestamp_value or None,
            "image_summary": self.image_summary,
        }

    def to_history_payload(self) -> dict:
        """Convert to the history message shape used by single-message moderation."""

        timestamp_value = humanize_timestamp(self.timestamp)

        return {
            "user_id": self.user_id,
            "username": self.username,
            "timestamp": timestamp_value or None,
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
                    "messages": [],
                    "__first_index": index,
                    "__first_timestamp": message.timestamp,
                }

            entry = grouped[user_id]
            entry_messages = entry["messages"]
            entry_messages.append(
                {
                    "message_id": message.message_id,
                    "timestamp": humanize_timestamp(message.timestamp) or None,
                    "content": message.content,
                    "image_summary": message.image_summary,
                    "order_index": index,
                }
            )
            entry["message_count"] += 1
            if message.timestamp and (
                not entry.get("__first_timestamp")
                or message.timestamp < entry["__first_timestamp"]
            ):
                entry["__first_timestamp"] = message.timestamp

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
                entry.get("__first_timestamp") or "",
                entry.get("__first_index", 0),
                entry["user_id"],
            )
        )

        for entry in ordered_users:
            entry.pop("__first_index", None)
            entry.pop("__first_timestamp", None)

        return ordered_users


# ============================================================
# Command Action Classes - extend ActionData for manual commands
# ============================================================


class CommandAction(ActionData):
    """Base class for manual moderation command actions.
    
    Extends ActionData with an execute method for direct execution
    without requiring a Discord message pivot.
    """

    async def execute(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Member,
        bot_instance: discord.Bot,
    ) -> None:
        """Execute the moderation action.

        Parameters
        ----------
        ctx:
            Slash command context.
        user:
            Guild member to apply the action to.
        bot_instance:
            Discord bot instance for scheduling tasks.
        """
        raise NotImplementedError("Subclasses must implement execute()")


class WarnCommand(CommandAction):
    """Warn action for manual commands."""

    def __init__(self, reason: str = "No reason provided."):
        """Initialize a warn action."""
        super().__init__(
            user_id="0",  # Will be set by caller
            action=ActionType.WARN,
            reason=reason,
        )

    async def execute(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Member,
        bot_instance: discord.Bot,
    ) -> None:
        """Execute warn action by creating embed and DM."""
        from modcord.util.discord_utils import (
            send_dm_to_user,
            build_dm_message,
            create_punishment_embed,
        )

        self.user_id = str(user.id)
        guild = ctx.guild

        try:
            try:
                await send_dm_to_user(
                    user, build_dm_message(ActionType.WARN, guild.name, self.reason)
                )
            except Exception:
                logger.debug("Failed to DM user for warning, continuing.")
            
            embed = await create_punishment_embed(
                ActionType.WARN, user, self.reason, issuer=bot_instance.user, bot_user=bot_instance.user
            )
            if embed and isinstance(ctx.channel, (discord.TextChannel, discord.Thread)):
                await ctx.channel.send(embed=embed)
        except Exception as exc:
            logger.error("Failed to process warn for user %s: %s", user.id, exc)


class TimeoutCommand(CommandAction):
    """Timeout action for manual commands."""

    def __init__(self, reason: str = "No reason provided.", duration_seconds: int = 600):
        """Initialize a timeout action."""
        super().__init__(
            user_id="0",  # Will be set by caller
            action=ActionType.TIMEOUT,
            reason=reason,
            timeout_duration=duration_seconds,
        )

    async def execute(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Member,
        bot_instance: discord.Bot,
    ) -> None:
        """Execute timeout action."""
        import datetime
        from modcord.util.discord_utils import (
            send_dm_to_user,
            build_dm_message,
            create_punishment_embed,
            format_duration,
        )

        self.user_id = str(user.id)
        guild = ctx.guild
        duration_seconds = self.timeout_duration or 600
        duration_label = format_duration(duration_seconds)
        until = discord.utils.utcnow() + datetime.timedelta(seconds=duration_seconds)

        try:
            await user.timeout(until, reason=f"Manual Mod: {self.reason}")
            try:
                await send_dm_to_user(
                    user,
                    build_dm_message(
                        ActionType.TIMEOUT, guild.name, self.reason, duration_label
                    ),
                )
            except Exception:
                logger.debug("Failed to DM user about timeout, continuing.")
            
            embed = await create_punishment_embed(
                ActionType.TIMEOUT,
                user,
                self.reason,
                duration_label,
                issuer=bot_instance.user,
                bot_user=bot_instance.user,
            )
            if embed and isinstance(ctx.channel, (discord.TextChannel, discord.Thread)):
                await ctx.channel.send(embed=embed)
        except Exception as exc:
            logger.error("Failed to timeout user %s: %s", user.id, exc)
            raise


class KickCommand(CommandAction):
    """Kick action for manual commands."""

    def __init__(self, reason: str = "No reason provided."):
        """Initialize a kick action."""
        super().__init__(
            user_id="0",  # Will be set by caller
            action=ActionType.KICK,
            reason=reason,
        )

    async def execute(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Member,
        bot_instance: discord.Bot,
    ) -> None:
        """Execute kick action."""
        from modcord.util.discord_utils import (
            send_dm_to_user,
            build_dm_message,
            create_punishment_embed,
        )

        self.user_id = str(user.id)
        guild = ctx.guild

        try:
            try:
                await send_dm_to_user(
                    user, build_dm_message(ActionType.KICK, guild.name, self.reason)
                )
            except Exception:
                logger.debug("Failed to DM user prior to kick, continuing.")
            
            await guild.kick(user, reason=f"Manual Mod: {self.reason}")
            embed = await create_punishment_embed(
                ActionType.KICK,
                user,
                self.reason,
                issuer=bot_instance.user,
                bot_user=bot_instance.user,
            )
            if embed and isinstance(ctx.channel, (discord.TextChannel, discord.Thread)):
                await ctx.channel.send(embed=embed)
        except Exception as exc:
            logger.error("Failed to kick user %s: %s", user.id, exc)
            raise


class BanCommand(CommandAction):
    """Ban action for manual commands."""

    def __init__(
        self, reason: str = "No reason provided.", duration_seconds: Optional[int] = None
    ):
        """Initialize a ban action.
        
        Parameters
        ----------
        reason:
            Reason for the ban.
        duration_seconds:
            Duration in seconds; None or 0 = permanent.
        """
        super().__init__(
            user_id="0",  # Will be set by caller
            action=ActionType.BAN,
            reason=reason,
            ban_duration=duration_seconds if duration_seconds and duration_seconds > 0 else None,
        )

    async def execute(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Member,
        bot_instance: discord.Bot,
    ) -> None:
        """Execute ban action."""
        import datetime
        from modcord.util.discord_utils import (
            send_dm_to_user,
            build_dm_message,
            create_punishment_embed,
            format_duration,
        )
        from modcord.bot.unban_scheduler import schedule_unban

        self.user_id = str(user.id)
        guild = ctx.guild
        duration_seconds = self.ban_duration or 0
        is_permanent = duration_seconds <= 0
        duration_label = "Till the end of time" if is_permanent else format_duration(duration_seconds)

        try:
            try:
                await send_dm_to_user(
                    user,
                    build_dm_message(ActionType.BAN, guild.name, self.reason, duration_label),
                )
            except Exception:
                logger.debug("Failed to DM user prior to ban, continuing.")
            
            await guild.ban(user, reason=f"Manual Mod: {self.reason}")
            embed = await create_punishment_embed(
                ActionType.BAN,
                user,
                self.reason,
                duration_label,
                issuer=bot_instance.user,
                bot_user=bot_instance.user,
            )
            if embed and isinstance(ctx.channel, (discord.TextChannel, discord.Thread)):
                await ctx.channel.send(embed=embed)
            
            # Schedule unban if not permanent
            if not is_permanent:
                try:
                    await schedule_unban(
                        guild=guild,
                        user_id=user.id,
                        channel=ctx.channel if isinstance(ctx.channel, (discord.TextChannel, discord.Thread)) else None,
                        duration_seconds=duration_seconds,
                        bot=bot_instance,
                        reason="Ban duration expired.",
                    )
                except Exception as exc:
                    logger.error("Failed to schedule unban for user %s: %s", user.id, exc)
        except Exception as exc:
            logger.error("Failed to ban user %s: %s", user.id, exc)
            raise