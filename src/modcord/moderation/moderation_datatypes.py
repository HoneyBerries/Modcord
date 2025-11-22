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
import PIL.Image
from typing import Any, Dict, Iterable, List, Sequence, Set
import discord
from modcord.util.logger import get_logger

logger = get_logger("moderation_datatypes")

def humanize_timestamp(value: str) -> str:
    """Return a human-readable timestamp (YYYY-MM-DD HH:MM:SS) in UTC.
    
    Ensures timestamps are never in the future by clamping to current time.

    Args:
        value (str): ISO 8601 timestamp string.

    Returns:
        str: Human-readable UTC timestamp.
    """
    # Parse ISO timestamp and ensure it's in UTC
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    
    # Convert to UTC if it has a different timezone
    if dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) != timezone.utc.utcoffset(None):
        dt = dt.astimezone(timezone.utc)
    elif dt.tzinfo is None:
        # If naive, assume UTC
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Clamp to current time if timestamp is in the future
    now_utc = datetime.now(timezone.utc)
    if dt > now_utc:
        logger.warning(
            "Timestamp %s is in the future, clamping to current time %s",
            dt.isoformat(),
            now_utc.isoformat()
        )
        dt = now_utc
    
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")

def format_past_actions(past_actions: List[dict]) -> List[dict]:
    """Format past moderation actions for inclusion in AI model payload.
    
    Args:
        past_actions (List[dict]): Raw past actions from database with keys:
            action_type, reason, timestamp, metadata.
    
    Returns:
        List[dict]: Formatted actions with keys: action, reason, timestamp, duration (optional).
    """
    formatted_past_actions = []
    for action in past_actions:
        formatted_action = {
            "action": action.get("action_type", "unknown"),
            "reason": action.get("reason", ""),
            "timestamp": humanize_timestamp(action.get("timestamp", "")) if action.get("timestamp") else None,
        }
        
        # Extract duration from metadata if present
        metadata = action.get("metadata", {})
        if isinstance(metadata, dict):
            # For ban actions, include ban_duration
            if "ban_duration" in metadata:
                ban_duration = metadata["ban_duration"]
                if ban_duration == -1:
                    formatted_action["duration"] = "permanent"
                elif ban_duration > 0:
                    formatted_action["duration"] = f"{ban_duration} minutes"
            # For timeout actions, include timeout_duration
            elif "timeout_duration" in metadata:
                timeout_duration = metadata["timeout_duration"]
                if timeout_duration == -1:
                    formatted_action["duration"] = "permanent"
                elif timeout_duration > 0:
                    formatted_action["duration"] = f"{timeout_duration} minutes"
        
        formatted_past_actions.append(formatted_action)
    
    return formatted_past_actions

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
    """Normalized moderation action payload.

    Attributes:
        user_id (str): Snowflake of target user, stored as string for JSON parity.
        action (ActionType): Moderation action to execute.
        reason (str): Human-readable explanation for auditing/logging.
        message_ids (List[str]): Related message IDs to operate on (deleted, audited, etc.).
        timeout_duration (int): Timeout duration in minutes (0 = not applicable, -1 = permanent, positive = duration).
        ban_duration (int): Ban duration in minutes (0 = not applicable, -1 = permanent, positive = duration).
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
        pil_image (Any | None): PIL.Image.Image object representing the image.
    """

    image_id: str
    pil_image: PIL.Image.Image | None = None

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
        guild_id (int | None): ID of the guild where the message was sent.
        channel_id (int | None): ID of the channel where the message was sent.
        images (List[ModerationImage]): List of images attached to the message.
        discord_message (discord.Message | None): Reference to the original Discord message object.
    """

    message_id: str
    user_id: str
    content: str
    timestamp: str
    guild_id: int | None
    channel_id: int | None
    images: List[ModerationImage] = field(default_factory=list)
    discord_message: "discord.Message | None" = None

    def to_model_payload(self, is_history: bool = False, image_id_map: Dict[str, int] | None = None) -> dict[str, Any]:
        """Convert message to AI model payload format.
        
        Args:
            is_history: Whether this message is historical context (not for action).
            image_id_map: Mapping of image_id -> index for PIL images list.
        
        Returns:
            dict: JSON-serializable message representation.
        """
        # Collect image IDs for this message
        msg_image_ids = []
        if self.images and image_id_map is not None:
            for img in self.images:
                if img.image_id and img.image_id in image_id_map:
                    msg_image_ids.append(img.image_id)
        
        return {
            "message_id": str(self.message_id),
            "timestamp": humanize_timestamp(self.timestamp) if self.timestamp else None,
            "content": self.content or ("[Images only]" if msg_image_ids else ""),
            "image_ids": msg_image_ids,
            "is_history": is_history,
        }

@dataclass(slots=True, eq=False)
class ModerationUser:
    """Represents a user in the moderation system with their messages and metadata.
    
    This class aggregates user information including their Discord roles and all
    messages they've sent. Messages are associated with users rather than containing
    duplicate user information.
    
    Attributes:
        user_id (str): Discord user snowflake ID.
        username (str): Discord username.
        roles (List[str]): List of role names the user has in the guild.
        join_date (str | None): ISO 8601 timestamp of when the user joined the guild.
        messages (List[ModerationMessage]): List of messages sent by this user.
        past_actions (List[dict]): List of past moderation actions taken on this user within the configured lookback window.
    """

    user_id: str
    username: str
    roles: List[str] = field(default_factory=list)
    join_date: str | None = None
    messages: List[ModerationMessage] = field(default_factory=list)
    past_actions: List[dict] = field(default_factory=list)

    # Make ModerationUser hashable and comparable by stable identifier only.
    def __hash__(self) -> int:
        return hash(self.user_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ModerationUser):
            return NotImplemented
        return self.user_id == other.user_id

    def add_message(self: ModerationUser, message: ModerationMessage) -> None:
        """Add a message to this user's message list.

        Args:
            message (ModerationMessage): The message to add.
        """
        self.messages.append(message)

    def to_model_payload(self, messages_payload: List[dict]) -> dict[str, Any]:
        """Convert user to AI model payload format with pre-formatted messages.
        
        Args:
            messages_payload: Pre-formatted messages list from message.to_model_payload().
        
        Returns:
            dict: JSON-serializable representation of the user.
        """
        return {
            "user_id": self.user_id,
            "username": self.username,
            "roles": self.roles,
            "join_date": humanize_timestamp(self.join_date) if self.join_date else None,
            "message_count": len(messages_payload),
            "messages": messages_payload,
            "past_actions": format_past_actions(self.past_actions),
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
    channel_name: str
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
    
    def to_multimodal_payload(self) -> tuple[Dict[str, Any], List[Any], Dict[str, int]]:
        """Convert batch to complete multimodal AI payload with images and deduplication.
        
        This is the primary method for preparing batches for AI inference. It handles:
        - User deduplication (merging current and history)
        - Message deduplication
        - Image collection and ID mapping
        - is_history flag setting
        - Complete payload construction
        
        Returns:
            Tuple of (json_payload, pil_images_list, image_id_map).
        """
        from collections import defaultdict
        
        pil_images: List[Any] = []
        image_id_map: Dict[str, int] = {}
        
        # Build sets of message IDs to determine which messages are historical
        current_message_ids: Set[str] = set()
        for user in self.users:
            for msg in user.messages:
                current_message_ids.add(str(msg.message_id))
        
        # Merge users by user_id, combining current and historical messages
        user_map: Dict[str, ModerationUser] = {}
        all_messages_by_user: Dict[str, List[tuple[ModerationMessage, bool]]] = defaultdict(list)
        
        # First, process current batch users (is_history=False for their messages)
        for user in self.users:
            user_id = str(user.user_id)
            if user_id not in user_map:
                user_map[user_id] = user
            for msg in user.messages:
                all_messages_by_user[user_id].append((msg, False))
        
        # Then, process history users (is_history=True for their messages)
        for user in self.history_users:
            user_id = str(user.user_id)
            if user_id not in user_map:
                # User only exists in history, use their data
                user_map[user_id] = user
            # Add historical messages (those not in current batch)
            for msg in user.messages:
                msg_id = str(msg.message_id)
                if msg_id not in current_message_ids:
                    all_messages_by_user[user_id].append((msg, True))
        
        total_messages = 0
        users_list = []
        
        # Process each unique user
        for user_id in sorted(user_map.keys()):
            user = user_map[user_id]
            messages_with_flags = all_messages_by_user[user_id]
            
            user_messages = []
            for msg, is_history in messages_with_flags:
                # Collect PIL images and build image ID map
                if msg.images:
                    for img in msg.images:
                        if img.pil_image and img.image_id:
                            if img.image_id not in image_id_map:
                                image_id_map[img.image_id] = len(pil_images)
                                pil_images.append(img.pil_image)
                
                # Convert message to payload
                msg_dict = msg.to_model_payload(is_history=is_history, image_id_map=image_id_map)
                user_messages.append(msg_dict)
                total_messages += 1
            
            # Convert user to payload with formatted messages
            user_dict = user.to_model_payload(messages_payload=user_messages)
            users_list.append(user_dict)
        
        payload = {
            "channel_id": str(self.channel_id),
            "channel_name": self.channel_name,
            "message_count": total_messages,
            "unique_user_count": len(user_map),
            "total_images": len(pil_images),
            "users": users_list,
        }
        
        return payload, pil_images, image_id_map

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
        from modcord.util.discord_utils import execute_moderation_notification

        self.user_id = str(user.id)

        try:
            await execute_moderation_notification(
                action_type=ActionType.WARN,
                user=user,
                guild=ctx.guild,
                reason=self.reason,
                channel=ctx.channel,
                duration_str=None,
                bot_user=bot_instance.user
            )
        except Exception as exc:
            logger.error("[MODERATION DATATYPES] Failed to process warn for user %s: %s", user.id, exc)


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
            execute_moderation_notification,
            format_duration,
        )

        self.user_id = str(user.id)
        duration_minutes = self.timeout_duration or 10
        # Handle -1 (permanent) by capping to Discord's 28-day max
        if duration_minutes == -1:
            duration_minutes = 28 * 24 * 60
        duration_seconds = duration_minutes * 60
        duration_label = format_duration(duration_seconds)
        until = discord.utils.utcnow() + datetime.timedelta(seconds=duration_seconds)

        try:
            await user.timeout(until, reason=f"Manual Mod: {self.reason}")
            await execute_moderation_notification(
                action_type=ActionType.TIMEOUT,
                user=user,
                guild=ctx.guild,
                reason=self.reason,
                channel=ctx.channel,
                duration_str=duration_label,
                bot_user=bot_instance.user
            )
        except Exception as exc:
            logger.error("[MODERATION DATATYPES] Failed to timeout user %s: %s", user.id, exc)
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
        from modcord.util.discord_utils import execute_moderation_notification

        self.user_id = str(user.id)

        try:
            await ctx.guild.kick(user, reason=f"Manual Mod: {self.reason}")
            await execute_moderation_notification(
                action_type=ActionType.KICK,
                user=user,
                guild=ctx.guild,
                reason=self.reason,
                channel=ctx.channel,
                duration_str=None,
                bot_user=bot_instance.user
            )
        except Exception as exc:
            logger.error("[MODERATION DATATYPES] Failed to kick user %s: %s", user.id, exc)
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
            execute_moderation_notification,
            format_duration,
        )
        from modcord.scheduler.unban_scheduler import schedule_unban

        self.user_id = str(user.id)
        duration_minutes = self.ban_duration or 0
        is_permanent = duration_minutes <= 0
        if is_permanent:
            duration_label = "Till the end of time"
            duration_seconds = 0
        else:
            duration_seconds = duration_minutes * 60
            duration_label = format_duration(duration_seconds)

        try:
            await ctx.guild.ban(user, reason=f"Manual Mod: {self.reason}")
            await execute_moderation_notification(
                action_type=ActionType.BAN,
                user=user,
                guild=ctx.guild,
                reason=self.reason,
                channel=ctx.channel,
                duration_str=duration_label,
                bot_user=bot_instance.user
            )
            
            # Schedule unban if not permanent
            if not is_permanent:
                try:
                    await schedule_unban(
                        guild=ctx.guild,
                        user_id=user.id,
                        channel=ctx.channel if isinstance(ctx.channel, (discord.TextChannel, discord.Thread)) else None,
                        duration_seconds=duration_seconds,
                        bot=bot_instance,
                        reason="Ban duration expired.",
                    )
                except Exception as exc:
                    logger.error("[MODERATION DATATYPES] Failed to schedule unban for user %s: %s", user.id, exc)
        except Exception as exc:
            logger.error("[MODERATION DATATYPES] Failed to ban user %s: %s", user.id, exc)
            raise