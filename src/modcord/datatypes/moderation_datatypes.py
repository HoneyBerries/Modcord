"""
Message and batch processing types for moderation.

This module defines data structures for representing messages, users, and batches
in the moderation pipeline. These types are used for normalizing Discord data
for AI processing.

Key Features:
- `ModerationImage`: Simplified image representation with SHA256 hash ID.
- `ModerationMessage`: Normalized representation of a Discord message.
- `ModerationUser`: User with their messages and metadata.
- `ModerationChannelBatch`: Container for batched messages and historical context.

Note: Serialization to AI payloads is handled by modcord.moderation.moderation_serialization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, List, Sequence

import discord

from modcord.datatypes.discord_datatypes import ChannelID, UserID, DiscordUsername, GuildID, MessageID
from modcord.datatypes.image_datatypes import ImageURL, ImageID
from modcord.util.logger import get_logger
from modcord.datatypes.action_datatypes import ActionData

logger = get_logger("moderation_datatypes")


@dataclass(slots=True)
class ModerationImage:
    """Simplified image representation with SHA256 hash ID and URL.

    Attributes:
        image_id (ImageID): First 8 characters of the SHA256 hash.
        image_url (ImageURL): URL of the image.
    """

    image_id: ImageID
    image_url: ImageURL


@dataclass(slots=True)
class ModerationMessage:
    """Normalized message data used to provide context to the moderation engine.
    
    Note: username is now stored at the ModerationUser level. This class only
    contains message-specific data, with user_id kept for reference purposes.

    Attributes:
        message_id (MessageID): Unique identifier for the message.
        user_id (UserID): Reference to the user who sent this message.
        content (str): Text content of the message.
        timestamp (datetime): UTC datetime of when the message was sent.
        guild_id (GuildID): ID of the guild where the message was sent.
        channel_id (ChannelID): ID of the channel where the message was sent.
        images (List[ModerationImage]): List of images attached to the message.
    """

    message_id: MessageID
    user_id: UserID
    content: str
    timestamp: datetime
    guild_id: GuildID
    channel_id: ChannelID
    images: List[ModerationImage] = field(default_factory=list)


@dataclass(slots=True)
class ModerationUser:
    """Represents a user in the moderation system with their messages and metadata.
    
    This class aggregates user information including their Discord roles and all
    messages they've sent. Messages are associated with users rather than containing
    duplicate user information.
    
    Attributes:
        user_id: Discord user snowflake ID.
        username: Discord username.
        join_date: Datetime of when the user joined the guild.
        discord_member: Reference to the Discord member object for applying moderation actions.
        discord_guild: Reference to the Discord guild object for applying moderation actions.
        roles: List of role names the user has in the guild.
        messages: List of messages sent by this user.
        past_actions: List of past moderation actions taken on this user.
    """

    user_id: UserID
    username: DiscordUsername
    join_date: datetime
    discord_member: discord.Member
    discord_guild: discord.Guild
    roles: List[str] = field(default_factory=list)
    messages: List[ModerationMessage] = field(default_factory=list)
    past_actions: List["ActionData"] = field(default_factory=list)

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


@dataclass(slots=True)
class ModerationChannelBatch:
    """Container for batched moderation data organized by users.
    
    This structure groups messages by user, allowing the AI model to reason
    about user behavior and context more effectively. Historical messages
    are also organized by user for consistency.

    Attributes:
        channel_id (ChannelID): ID of the channel the batch belongs to.
        users (List[ModerationUser]): List of users with their messages in the batch.
        history_users (List[ModerationUser]): Historical users for context.
    """

    guild_id: GuildID
    channel_id: ChannelID
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
