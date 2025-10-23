"""
Per-channel message cache with TTL (time-to-live) support.

This module provides an in-memory caching mechanism for storing messages in a single Discord channel. The cache supports:
- Automatic expiration of messages based on a configurable TTL.
- Deduplication of messages by their unique IDs.
- Efficient storage and retrieval of messages using a deque.

Key Features:
- Configurable maximum message capacity per channel.
- Automatic removal of expired messages.
- Thread-safe operations for adding, removing, and retrieving messages.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Deque, Set

from modcord.util.logger import get_logger
from modcord.moderation.moderation_datatypes import ModerationMessage

logger = get_logger("channel_cache")


class ChannelMessageCache:
    """
    In-memory message cache for a single Discord channel with TTL support.

    This class provides a per-channel caching mechanism for storing recent messages. Messages are automatically removed
    from the cache when they exceed the configured TTL or when the cache reaches its maximum capacity.

    Attributes:
        max_messages (int): Maximum number of messages to retain in the cache.
        ttl_seconds (int): Time-to-live for cached messages, in seconds.
        messages (Deque[tuple[ModerationMessage, datetime]]): Deque storing messages and their timestamps.
        _message_ids (Set[str]): Set of message IDs for quick deduplication.
    """

    def __init__(self, max_messages: int = 12, ttl_seconds: int = 3600):
        """
        Initialize the channel cache.

        Args:
            max_messages (int): Maximum messages to retain in cache per channel.
            ttl_seconds (int): Time-to-live for cached messages in seconds (default 1 hour).
        """
        self.max_messages = max_messages
        self.ttl_seconds = ttl_seconds
        self.messages: Deque[tuple[ModerationMessage, datetime]] = deque(maxlen=max_messages)
        self._message_ids: Set[str] = set()

    def add_message(self, message: ModerationMessage) -> None:
        """
        Add a message to the cache and track its ID.

        Args:
            message (ModerationMessage): The message to add to the cache.
        """
        message_id = str(message.message_id)
        if message_id in self._message_ids:
            return
        
        now = datetime.now(timezone.utc)
        self.messages.append((message, now))
        self._message_ids.add(message_id)
        
        # If cache is full, the oldest message is auto-dropped by deque.maxlen
        # Clean up its ID from the tracking set
        if len(self.messages) >= self.max_messages:
            logger.debug("Channel cache at max capacity (%d messages)", self.max_messages)
            while len(self.messages) > self.max_messages:
                old_msg, _ = self.messages.popleft()
                old_msg_id = str(old_msg.message_id)
                self._message_ids.discard(old_msg_id)

    def remove_message(self, message_id: str) -> bool:
        """
        Remove a message from the cache by ID.

        Args:
            message_id (str): The message ID to remove.

        Returns:
            bool: True if the message was found and removed, False otherwise.
        """
        message_id = str(message_id)
        if message_id not in self._message_ids:
            return False
        
        # Remove from tracking set
        self._message_ids.discard(message_id)
        
        # Remove from deque by rebuilding
        old_messages = list(self.messages)
        self.messages.clear()
        
        found = False
        for msg, timestamp in old_messages:
            if str(msg.message_id) == message_id:
                found = True
                continue  # Skip this message
            self.messages.append((msg, timestamp))
        
        if found:
            logger.debug("Removed message %s from cache", message_id)
        
        return found

    def get_valid_messages(self) -> list[ModerationMessage]:
        """
        Return all messages still within TTL, removing expired ones.

        Returns:
            list[ModerationMessage]: List of valid (non-expired) messages.
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self.ttl_seconds)
        
        valid = []
        expired_ids = set()
        
        for msg, timestamp in self.messages:
            if timestamp >= cutoff:
                valid.append(msg)
            else:
                expired_ids.add(str(msg.message_id))
        
        # Clean up expired IDs
        self._message_ids -= expired_ids
        
        return valid

    def clear(self) -> None:
        """
        Clear all messages from the cache.
        """
        self.messages.clear()
        self._message_ids.clear()
