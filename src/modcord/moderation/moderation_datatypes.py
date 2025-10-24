"""
Utility types for moderation actions and message payloads.

This module defines the data structures and enumerations used for moderation actions, message payloads, and batch processing. These types are used throughout the moderation pipeline to normalize and serialize data for AI processing and Discord API interactions.

Key Features:
- `ActionType`: Enum for supported moderation actions (e.g., BAN, WARN, DELETE).
- `ActionData`: Represents a moderation action with metadata (e.g., user ID, reason, message IDs).
- `ModerationMessage`: Normalized representation of a Discord message, including text and images.
- `ModerationChannelBatch`: Container for batched messages and historical context per channel.
- Command action classes (e.g., `WarnCommand`, `TimeoutCommand`) for manual moderation commands.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, List, Optional, Sequence
import discord
from modcord.util.logger import get_logger

logger = get_logger("moderation_datatypes")

def humanize_timestamp(value: str) -> str:
    """Return a human-readable timestamp (YYYY-MM-DD HH:MM:SS) in UTC.

    Args:
        value (str): ISO 8601 timestamp string.

    Returns:
        str: Human-readable UTC timestamp.
    """
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
        user_id (str): Snowflake of target user, stored as string for JSON parity.
        action (ActionType): Moderation action to execute.
        reason (str): Human-readable explanation for auditing/logging.
        message_ids (List[str]): Related message IDs to operate on (deleted, audited, etc.).
        timeout_duration (Optional[int]): Timeout duration in minutes (0 = not applicable, -1 = permanent, positive = duration).
        ban_duration (Optional[int]): Ban duration in minutes (0 = not applicable, -1 = permanent, positive = duration).
    """

    user_id: str
    action: ActionType
    reason: str
    timeout_duration: int
    ban_duration: int
    message_ids: List[str] = field(default_factory=list)

    def add_message_ids(self, *message_ids: str) -> None:
        """Append one or more message identifiers to the action payload.

        Args:
            *message_ids: Discord message identifiers associated with the moderation action.
        """
        for raw_mid in message_ids:
            mid = str(raw_mid).strip()
            if not mid:
                continue
            if mid not in self.message_ids:
                self.message_ids.append(mid)

    def replace_message_ids(self, message_ids: Iterable[str]) -> None:
        """Replace the tracked message identifiers with the provided iterable.

        Args:
            message_ids (Iterable[str]): Iterable of message identifiers that should overwrite the current list.
        """
        self.message_ids.clear()
        self.add_message_ids(*message_ids)

    def to_wire_dict(self) -> dict:
        """Return a JSON-serializable dictionary representing this action.

        Returns:
            dict: JSON-serializable representation of the action.
        """
        return {
            "user_id": self.user_id,
            "action": self.action.value,
            "reason": self.reason,
            "message_ids": list(self.message_ids),
            "timeout_duration": self.timeout_duration,
            "ban_duration": self.ban_duration,
        }

@dataclass(slots=True)
class ModerationImage:
    """Simplified image representation with SHA256 hash ID and PIL image.

    Attributes:
        image_id (str): First 8 characters of the SHA256 hash.
        pil_image (Optional[Any]): PIL.Image.Image object representing the image.
    """

    image_id: str
    pil_image: Optional[Any] = None

@dataclass(slots=True)
class ModerationMessage:
    """Normalized message data used to provide context to the moderation engine.
    
    Note: username is now stored at the ModerationUser level. This class only
    contains message-specific data, with user_id kept for reference purposes.

    Attributes:
        message_id (str): Unique identifier for the message.
        user_id (str): Reference to the user who sent this message.
        content (str): Text content of the message.
        timestamp (str): ISO 8601 timestamp of when the message was sent.
        guild_id (Optional[int]): ID of the guild where the message was sent.
        channel_id (Optional[int]): ID of the channel where the message was sent.
        images (List[ModerationImage]): List of images attached to the message.
        discord_message (Optional[discord.Message]): Reference to the original Discord message object.
    """

    message_id: str
    user_id: str
    content: str
    timestamp: str
    guild_id: Optional[int]
    channel_id: Optional[int]
    images: List[ModerationImage] = field(default_factory=list)
    discord_message: "discord.Message | None" = None

@dataclass(slots=True)
class ModerationUser:
    """Represents a user in the moderation system with their messages and metadata.
    
    This class aggregates user information including their Discord roles and all
    messages they've sent. Messages are associated with users rather than containing
    duplicate user information.
    
    Attributes:
        user_id (str): Discord user snowflake ID.
        username (str): Discord username.
        roles (List[str]): List of role names the user has in the guild.
        join_date (Optional[str]): ISO 8601 timestamp of when the user joined the guild.
        messages (List[ModerationMessage]): List of messages sent by this user.
    """

    user_id: str
    username: str
    roles: List[str] = field(default_factory=list)
    join_date: Optional[str] = None
    messages: List[ModerationMessage] = field(default_factory=list)

    def add_message(self: ModerationUser, message: ModerationMessage) -> None:
        """Add a message to this user's message list.

        Args:
            message (ModerationMessage): The message to add.
        """
        self.messages.append(message)

    def to_model_payload(self: ModerationUser) -> dict[str, Any]:
        """Convert to the dictionary structure expected by the AI model.
        
        Returns a JSON payload with user metadata and all their messages.

        Returns:
            dict: JSON-serializable representation of the user.
        """
        join_date_value = None
        if self.join_date:
            join_date_value = humanize_timestamp(self.join_date)

        return {
            "user_id": self.user_id,
            "username": self.username,
            "roles": self.roles,
            "join_date": join_date_value,
            "message_count": len(self.messages),
            "messages": [{"message_id": msg.message_id, "content": msg.content, "timestamp": humanize_timestamp(msg.timestamp)} for msg in self.messages],
        }

@dataclass(slots=True)
class ModerationChannelBatch:
    """Container for batched moderation data organized by users.
    
    This structure groups messages by user, allowing the AI model to reason
    about user behavior and context more effectively. Historical messages
    are also organized by user for consistency.

    Attributes:
        channel_id (int): ID of the channel the batch belongs to.
        users (List[ModerationUser]): List of users with their messages in the batch.
        history_users (List[ModerationUser]): Historical users for context.
    """

    channel_id: int
    users: List[ModerationUser] = field(default_factory=list)
    history_users: List[ModerationUser] = field(default_factory=list)

    def add_user(self, user: ModerationUser) -> None:
        """Add a user with their messages to the batch.

        Args:
            user (ModerationUser): The user to add.
        """
        self.users.append(user)

    def extend_users(self, users: Sequence[ModerationUser]) -> None:
        """Extend the batch with a sequence of users.

        Args:
            users (Sequence[ModerationUser]): Users to add to the batch.
        """
        self.users.extend(users)

    def set_history(self, history_users: Sequence[ModerationUser]) -> None:
        """Set the historical context users for the batch.

        Args:
            history_users (Sequence[ModerationUser]): Historical users to set.
        """
        self.history_users = list(history_users)

    def is_empty(self) -> bool:
        """Check if the batch has no users or all users have no messages.

        Returns:
            bool: True if the batch is empty, False otherwise.
        """
        return not self.users or all(not user.messages for user in self.users)

    def to_model_payload(self) -> List[dict]:
        """Convert batch users to the payload structure expected by the AI model.

        Returns:
            List[dict]: List of user payloads.
        """
        return [user.to_model_payload() for user in self.users]

    def history_to_model_payload(self) -> List[dict]:
        """Convert historical users to the payload structure expected by the AI model.

        Returns:
            List[dict]: List of historical user payloads.
        """
        return [user.to_model_payload() for user in self.history_users]

# ============================================================
# Command Action Classes - extend ActionData for manual commands
# ============================================================

class CommandAction(ActionData):
    """Base class for manual moderation command actions.
    
    Extends ActionData with an execute method for direct execution
    without requiring a Discord message pivot.
    
    Attributes:
        user_id (str): Snowflake of the target user.
        action (ActionType): Moderation action to execute.
        reason (str): Reason for the action.
    """

    async def execute(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Member,
        bot_instance: discord.Bot,
    ) -> None:
        """Execute the moderation action.

        Args:
            ctx (discord.ApplicationContext): Slash command context.
            user (discord.Member): Guild member to apply the action to.
            bot_instance (discord.Bot): Discord bot instance for scheduling tasks.
        """
        raise NotImplementedError("Subclasses must implement execute()")

class WarnCommand(CommandAction):
    """Warn action for manual commands."""

    def __init__(self, reason: str = "No reason provided."):
        """Initialize a warn action.

        Args:
            reason (str): Reason for the warning.
        """
        super().__init__(
            user_id="0",  # Will be set by caller
            action=ActionType.WARN,
            reason=reason,
            timeout_duration=0,
            ban_duration=0,
        )

    async def execute(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Member,
        bot_instance: discord.Bot,
    ) -> None:
        """Execute warn action by creating embed and DM.

        Args:
            ctx (discord.ApplicationContext): Slash command context.
            user (discord.Member): Guild member to warn.
            bot_instance (discord.Bot): Discord bot instance.
        """
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

    def __init__(self, reason: str = "No reason provided.", duration_minutes: int = 10):
        """Initialize a timeout action.
        
        Parameters
        ----------
        reason:
            Reason for the timeout.
        duration_minutes:
            Duration in minutes; -1 = permanent (capped to Discord's 28-day max), positive = duration, 0 = not applicable.
        """
        super().__init__(
            user_id="0",  # Will be set by caller
            action=ActionType.TIMEOUT,
            reason=reason,
            timeout_duration=duration_minutes,
            ban_duration=0,
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
        duration_minutes = self.timeout_duration or 10
        # Handle -1 (permanent) by capping to Discord's 28-day max
        if duration_minutes == -1:
            duration_minutes = 28 * 24 * 60
        duration_seconds = duration_minutes * 60
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
            timeout_duration=0,
            ban_duration=0,
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
        self, duration_minutes: int, reason: str = "No reason provided."
    ):
        """Initialize a ban action.
        
        Parameters
        ----------
        duration_minutes:
            Duration in minutes; -1 = permanent, None or 0 = not applicable.
        reason:
            Reason for the ban.
        """
        super().__init__(
            user_id="0",  # Will be set by caller
            action=ActionType.BAN,
            reason=reason,
            timeout_duration=0,
            ban_duration=duration_minutes
        )

    async def execute(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Member,
        bot_instance: discord.Bot,
    ) -> None:
        """Execute ban action."""
        from modcord.util.discord_utils import (
            send_dm_to_user,
            build_dm_message,
            create_punishment_embed,
            format_duration,
        )
        from modcord.scheduler.unban_scheduler import schedule_unban

        self.user_id = str(user.id)
        guild = ctx.guild
        duration_minutes = self.ban_duration or 0
        is_permanent = duration_minutes <= 0
        if is_permanent:
            duration_label = "Till the end of time"
            duration_seconds = 0
        else:
            duration_seconds = duration_minutes * 60
            duration_label = format_duration(duration_seconds)

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