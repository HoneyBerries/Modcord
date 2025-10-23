"""Dynamic message history cache with Discord API fallback.

This module provides a message cache that:
1. Stores recent messages in memory per-channel (bounded deque)
2. On demand, fetches older messages from Discord API if cache is insufficient
3. Dynamically fetches as many messages as needed for context
4. Provides cache TTL and size limits

The cache is designed to handle bot restarts gracefully by fetching historical
context directly from Discord when needed, rather than relying solely on
messages seen at runtime.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Optional, Deque, Set

import discord

from modcord.util.logger import get_logger
from modcord.util.moderation_datatypes import ModerationImage, ModerationMessage
from modcord.util.image_utils import generate_image_hash_id

logger = get_logger("message_cache")


IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")


def _is_image_attachment(attachment: discord.Attachment) -> bool:
    """Return True when the attachment can be treated as an image."""

    content_type = (attachment.content_type or "").lower()
    if content_type.startswith("image/"):
        return True

    if attachment.width is not None and attachment.height is not None:
        return True

    filename = (attachment.filename or "").lower()
    return filename.endswith(IMAGE_EXTENSIONS)


def _build_moderation_images(message: discord.Message) -> list[ModerationImage]:
    """Convert Discord attachments to ModerationImage structures.
    
    Note: PIL images are NOT downloaded here. Images are created with hash IDs only.
    Download should happen separately in the bot cog.
    """

    images: list[ModerationImage] = []

    for attachment in message.attachments:
        if not _is_image_attachment(attachment):
            continue

        # Generate hash ID from URL
        image_id = generate_image_hash_id(attachment.url)
        
        images.append(
            ModerationImage(
                image_id=image_id,
                pil_image=None,  # Not downloaded in cache layer
            )
        )

    return images


class ChannelMessageCache:
    """In-memory message cache for a single Discord channel with TTL support."""

    def __init__(self, max_messages: int = 500, ttl_seconds: int = 3600):
        """
        Initialize the channel cache.

        Parameters
        ----------
        max_messages:
            Maximum messages to retain in cache per channel.
        ttl_seconds:
            Time-to-live for cached messages in seconds (default 1 hour).
        """
        self.max_messages = max_messages
        self.ttl_seconds = ttl_seconds
        self.messages: Deque[tuple[ModerationMessage, datetime]] = deque(maxlen=max_messages)
        self._message_ids: Set[str] = set()

    def add_message(self, message: ModerationMessage) -> None:
        """Add a message to the cache and track its ID."""
        message_id = str(message.message_id)
        if message_id in self._message_ids:
            return  # Duplicate, skip
        
        now = datetime.now(timezone.utc)
        self.messages.append((message, now))
        self._message_ids.add(message_id)
        
        # If cache is full, the oldest message is auto-dropped by deque.maxlen
        # Clean up its ID from the tracking set
        if len(self.messages) >= self.max_messages:
            logger.debug("Channel cache at max capacity (%d messages)", self.max_messages)

    def get_valid_messages(self) -> list[ModerationMessage]:
        """Return all messages still within TTL, removing expired ones."""
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
        """Clear all messages from the cache."""
        self.messages.clear()
        self._message_ids.clear()


class MessageHistoryCache:
    """
    Dynamic message history cache with Discord API fallback.
    
    Stores recent messages per-channel and fetches from Discord API when
    historical context is needed but not yet cached.
    """

    def __init__(
        self,
        max_messages_per_channel: int = 500,
        cache_ttl_seconds: int = 3600,
        api_fetch_limit: int = 100,
    ):
        """
        Initialize the message history cache.

        Parameters
        ----------
        max_messages_per_channel:
            Maximum cached messages per channel.
        cache_ttl_seconds:
            TTL for cached messages in seconds.
        api_fetch_limit:
            Max messages to fetch from Discord API in one call.
        """
        self.max_messages_per_channel = max_messages_per_channel
        self.cache_ttl_seconds = cache_ttl_seconds
        self.api_fetch_limit = api_fetch_limit
        
        # Per-channel caches
        self.channel_caches: dict[int, ChannelMessageCache] = defaultdict(
            lambda: ChannelMessageCache(max_messages_per_channel, cache_ttl_seconds)
        )
        
        # Track bot instance for API calls
        self.bot: Optional[discord.Client] = None
        
        logger.info(
            "MessageHistoryCache initialized (max %d msgs/channel, TTL %d sec)",
            max_messages_per_channel,
            cache_ttl_seconds,
        )

    def set_bot(self, bot: discord.Client) -> None:
        """Set the Discord bot instance for API calls."""
        self.bot = bot

    def add_message(self, channel_id: int, message: ModerationMessage) -> None:
        """Add a message to the channel's cache."""
        cache = self.channel_caches[channel_id]
        cache.add_message(message)

    def get_cached_messages(self, channel_id: int) -> list[ModerationMessage]:
        """Get valid (non-expired) cached messages for a channel."""
        cache = self.channel_caches[channel_id]
        return cache.get_valid_messages()

    async def fetch_history_for_context(
        self,
        channel_id: int,
        limit: int,
        exclude_message_ids: Optional[set[str]] = None,
    ) -> list[ModerationMessage]:
        """
        Fetch message history for context, using cache and Discord API as fallback.

        Returns the most recent `limit` messages from the channel, excluding
        the specified message IDs. First tries cached messages; if insufficient,
        fetches from Discord API.

        Parameters
        ----------
        channel_id:
            The Discord channel ID.
        limit:
            Number of messages to return.
        exclude_message_ids:
            Set of message IDs to exclude (e.g., current batch messages).

        Returns
        -------
        list[ModerationMessage]
            Up to `limit` historical messages, most recent first (oldest to newest order).
        """
        if limit <= 0:
            return []

        exclude_ids = exclude_message_ids or set()

        # 1. Get cached messages (already filtered by TTL)
        cached = self.get_cached_messages(channel_id)
        cached_valid = [m for m in cached if str(m.message_id) not in exclude_ids]

        # 2. If cached messages are sufficient, return them
        if len(cached_valid) >= limit:
            return cached_valid[-limit:]  # Return newest `limit` messages

        # 3. If insufficient, try to fetch from Discord API
        api_messages = []
        if self.bot:
            try:
                api_messages = await self._fetch_from_discord(
                    channel_id, 
                    limit - len(cached_valid),
                    exclude_ids,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to fetch history from Discord for channel %s: %s",
                    channel_id,
                    exc,
                )

        # 4. Combine and return (cached + API fetched, deduplicated)
        combined_ids = {str(m.message_id) for m in cached_valid}
        for msg in api_messages:
            if str(msg.message_id) not in combined_ids:
                cached_valid.append(msg)
                combined_ids.add(str(msg.message_id))

        return cached_valid[-limit:] if cached_valid else []

    async def _fetch_from_discord(
        self,
        channel_id: int,
        limit: int,
        exclude_ids: set[str],
    ) -> list[ModerationMessage]:
        """
        Fetch messages from Discord API for a channel.

        Parameters
        ----------
        channel_id:
            The Discord channel ID.
        limit:
            Max messages to fetch.
        exclude_ids:
            Message IDs to exclude from results.

        Returns
        -------
        list[ModerationMessage]
            Converted Discord messages, excluding specified IDs.
        """
        if not self.bot or limit <= 0:
            return []

        try:
            channel = self.bot.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                logger.debug("Channel %s not found or not a text channel", channel_id)
                return []

            # Fetch messages; we may fetch more than `limit` to skip excluded ones
            fetch_count = min(limit * 2, self.api_fetch_limit)
            messages = []

            now_utc = datetime.now(timezone.utc)
            max_age_cutoff: Optional[datetime] = None
            if self.cache_ttl_seconds > 0:
                max_age_cutoff = now_utc - timedelta(seconds=self.cache_ttl_seconds)

            async for discord_msg in channel.history(limit=fetch_count):
                if str(discord_msg.id) in exclude_ids:
                    continue
                
                # Skip ignored authors (bots, admins)
                if discord_msg.author.bot:
                    continue
                
                created_at = discord_msg.created_at
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                if max_age_cutoff and created_at < max_age_cutoff:
                    continue

                content = (discord_msg.clean_content or "").strip()
                images = _build_moderation_images(discord_msg)

                # Skip messages that have neither text nor image attachments
                if not content and not images:
                    continue

                mod_msg = ModerationMessage(
                    message_id=str(discord_msg.id),
                    user_id=str(discord_msg.author.id),
                    username=str(discord_msg.author),
                    content=content,
                    timestamp=created_at.astimezone(timezone.utc)
                    .replace(microsecond=0)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    guild_id=discord_msg.guild.id if discord_msg.guild else None,
                    channel_id=channel_id,
                    images=images,
                    discord_message=None,
                )
                messages.append(mod_msg)

                if len(messages) >= limit:
                    break

            logger.debug(
                "Fetched %d messages from Discord API for channel %s",
                len(messages),
                channel_id,
            )
            return messages

        except discord.Forbidden:
            logger.warning("No permission to read history from channel %s", channel_id)
            return []
        except discord.NotFound:
            logger.warning("Channel %s not found", channel_id)
            return []
        except Exception as exc:
            logger.error(
                "Unexpected error fetching history from channel %s: %s",
                channel_id,
                exc,
            )
            return []

    def clear_channel_cache(self, channel_id: int) -> None:
        """Clear the cache for a specific channel."""
        if channel_id in self.channel_caches:
            self.channel_caches[channel_id].clear()
            logger.debug("Cleared cache for channel %s", channel_id)

    def clear_all(self) -> None:
        """Clear all cached messages."""
        self.channel_caches.clear()
        logger.info("Cleared all message caches")


# Global message history cache instance
# Instantiated with default values; will be reconfigured if cache config is available
message_history_cache = MessageHistoryCache()


def initialize_cache_from_config(app_config) -> None:
    """
    Initialize message cache with settings from app_config.
    
    Call this after app_config is loaded to apply user-configured cache settings.
    """
    global message_history_cache
    try:
        if not app_config or not hasattr(app_config, "ai_settings"):
            return
        
        ai_settings = app_config.ai_settings
        cache_cfg = ai_settings.get("cache", {}) if isinstance(ai_settings, dict) else {}
        
        if not cache_cfg:
            return
        
        max_msgs = int(cache_cfg.get("max_messages_per_channel", 500))
        ttl_secs = int(cache_cfg.get("cache_ttl_seconds", 3600))
        api_limit = int(cache_cfg.get("api_fetch_limit", 100))
        
        # Recreate with config values
        message_history_cache = MessageHistoryCache(
            max_messages_per_channel=max_msgs,
            cache_ttl_seconds=ttl_secs,
            api_fetch_limit=api_limit,
        )
        
        logger.info(
            "Message cache configured from app_config: "
            "max_msgs=%d, ttl=%ds, api_limit=%d",
            max_msgs,
            ttl_secs,
            api_limit,
        )
    except Exception as exc:
        logger.warning("Failed to configure cache from app_config: %s", exc)
