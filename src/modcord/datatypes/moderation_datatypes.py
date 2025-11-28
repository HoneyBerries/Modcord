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
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Sequence, Set

import PIL.Image
import discord

from modcord.datatypes.discord_datatypes import ChannelID, UserID, DiscordUsername, GuildID, MessageID
from modcord.datatypes.image_datatypes import ImageURL, ImageID
from modcord.util.format_utils import humanize_timestamp, format_past_actions
from modcord.util.logger import get_logger
from modcord.datatypes.action_datatypes import ActionData

logger = get_logger("moderation_datatypes")


@dataclass(slots=True)
class ModerationImage:
    """Simplified image representation with SHA256 hash ID, URL, and optional PIL image.

    Attributes:
        image_id (ImageID): First 8 characters of the SHA256 hash.
        image_url (ImageURL): URL of the image for downloading.
        pil_image (PIL.Image.Image): PIL.Image.Image object representing the image.
    """

    image_id: ImageID
    image_url: ImageURL
    pil_image: PIL.Image.Image


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

    def convert_message_to_model_payload(self, is_history: bool, image_id_map: Dict[str, int]) -> dict[str, Any]:
        """Convert message to AI model payload format.
        
        Args:
            is_history: Whether this message is historical context (not for action).
            image_id_map: Mapping of image_id string -> index for PIL images list.
        
        Returns:
            dict: JSON-serializable message representation.
        """
        # Collect image IDs for this message
        msg_image_ids: List[str] = []
        if self.images and image_id_map is not None:
            for img in self.images:
                if img.image_id:
                    img_id_str = str(img.image_id)
                    if img_id_str in image_id_map:
                        msg_image_ids.append(img_id_str)
        
        return {
            "message_id": str(self.message_id),
            "timestamp": humanize_timestamp(self.timestamp),
            "content": self.content or ("[Images only]" if msg_image_ids else ""),
            "image_ids": msg_image_ids,
            "is_history": is_history,
        }

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

    def convert_user_to_model_payload(self, messages_payload: List[dict]) -> dict[str, Any]:
        """Convert user to AI model payload format with pre-formatted messages.
        
        Args:
            messages_payload: Pre-formatted messages list from message.convert_message_to_model_payload().
        
        Returns:
            dict: JSON-serializable representation of the user.
        """
        return {
            "user_id": str(self.user_id),
            "username": str(self.username),
            "roles": self.roles,
            "join_date": humanize_timestamp(self.join_date),
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
        channel_id (ChannelID): ID of the channel the batch belongs to.
        users (List[ModerationUser]): List of users with their messages in the batch.
        history_users (List[ModerationUser]): Historical users for context.
    """

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
                            img_id_str = str(img.image_id)
                            if img_id_str not in image_id_map:
                                image_id_map[img_id_str] = len(pil_images)
                                pil_images.append(img.pil_image)
                
                # Convert message to payload
                msg_dict = msg.convert_message_to_model_payload(is_history=is_history, image_id_map=image_id_map)
                user_messages.append(msg_dict)
                total_messages += 1
            
            # Convert user to payload with formatted messages
            user_dict = user.convert_user_to_model_payload(messages_payload=user_messages)
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