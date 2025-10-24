"""
Message history cache with Discord API fallback for missing messages.

This module provides a caching mechanism for storing recent messages per channel, with the ability to fetch additional historical messages from the Discord API when needed. It is designed to optimize performance by reducing redundant API calls while ensuring historical context is available for moderation tasks.

Key Features:
- Per-channel message caching with configurable TTL (time-to-live).
- Discord API fallback for fetching uncached historical messages.
- Deduplication of cached and fetched messages.
- Support for extracting and normalizing message content, including embeds and image attachments.
- Global cache instance for centralized access.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord

from modcord.util.logger import get_logger
from modcord.moderation.moderation_datatypes import ModerationImage, ModerationMessage
from modcord.history.channel_cache import ChannelMessageCache
from modcord.util.image_utils import generate_image_hash_id

logger = get_logger("history_cache")

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")


def _is_image_attachment(attachment: discord.Attachment) -> bool:
    """Return True when the attachment can be treated as an image.

    Args:
        attachment (discord.Attachment): The attachment to check.

    Returns:
        bool: True if the attachment is an image, False otherwise.
    """
    content_type = (attachment.content_type or "").lower()
    if content_type.startswith("image/"):
        return True

    if attachment.width is not None and attachment.height is not None:
        return True

    filename = (attachment.filename or "").lower()
    return filename.endswith(IMAGE_EXTENSIONS)


def _build_moderation_images(message: discord.Message) -> list[ModerationImage]:
    """Convert Discord attachments to ModerationImage structures.

    Args:
        message (discord.Message): The message containing attachments.

    Returns:
        list[ModerationImage]: List of ModerationImage objects for image attachments.
    """
    images: list[ModerationImage] = []

    for attachment in message.attachments:
        if not _is_image_attachment(attachment):
            continue

        image_id = generate_image_hash_id(attachment.url)
        images.append(
            ModerationImage(
                image_id=image_id,
                pil_image=None,
            )
        )

    return images


def _extract_embed_content(message: discord.Message) -> str:
    """Extract and format content from message embeds.

    Args:
        message (discord.Message): The message containing embeds.

    Returns:
        str: Formatted content extracted from embeds.
    """
    if not message.embeds:
        return ""
    
    embed_parts = []
    for embed in message.embeds:
        parts = []
        
        if embed.title:
            parts.append(f"[Embed Title: {embed.title}]")
        
        if embed.description:
            parts.append(f"[Embed Description: {embed.description}]")
        
        if embed.fields:
            for field in embed.fields:
                if field.name or field.value:
                    parts.append(f"[Embed Field - {field.name}: {field.value}]")
        
        if embed.footer and embed.footer.text:
            parts.append(f"[Embed Footer: {embed.footer.text}]")
        
        if embed.author and embed.author.name:
            parts.append(f"[Embed Author: {embed.author.name}]")
        
        if parts:
            embed_parts.append(" ".join(parts))
    
    return "\n".join(embed_parts) if embed_parts else ""


class GlobalHistoryCacheManager:
    """
    Global manager for per-channel message history caching with Discord API fallback.

    This class maintains in-memory caches of recent messages for each channel, supporting automatic expiration (TTL) and deduplication. When additional historical context is required and not present in the cache, it transparently fetches messages from the Discord API, minimizing redundant API calls. Designed for moderation and context-aware features.

    Attributes:
        max_messages_per_channel (int): Maximum number of messages to retain per channel cache.
        cache_ttl_seconds (int): Time-to-live for cached messages, in seconds.
        api_fetch_limit (int): Maximum number of messages to fetch from the Discord API in a single call.
        channel_caches (dict[int, ChannelMessageCache]): Mapping of channel IDs to their message caches.
        bot (Optional[discord.Client]): Discord bot instance used for API operations.
    """

    def __init__(
        self,
        max_messages_per_channel: int = 24,
        cache_ttl_seconds: int = 3600,
        api_fetch_limit: int = 100,
    ):
        """
        Initialize the message history cache.

        Args:
            max_messages_per_channel (int): Maximum cached messages per channel.
            cache_ttl_seconds (int): TTL for cached messages in seconds.
            api_fetch_limit (int): Max messages to fetch from Discord API in one call.
        """
        self.max_messages_per_channel = max_messages_per_channel
        self.cache_ttl_seconds = cache_ttl_seconds
        self.api_fetch_limit = api_fetch_limit
        
        # Per-channel caches
        self.channel_caches: dict[int, ChannelMessageCache] = defaultdict(
            lambda: ChannelMessageCache(max_messages_per_channel, cache_ttl_seconds)
        )
        
        # Bot instance for API calls
        self.bot: Optional[discord.Client] = None
        
        logger.info(
            "GlobalHistoryCacheManager initialized (max %d msgs/channel, TTL %d sec)",
            max_messages_per_channel,
            cache_ttl_seconds,
        )

    def set_bot(self, bot: discord.Client) -> None:
        """Set the Discord bot instance for API calls.

        Args:
            bot (discord.Client): The Discord bot instance.
        """
        self.bot = bot

    def add_message(self, channel_id: int, message: ModerationMessage) -> None:
        """Add a message to the channel's cache.

        Args:
            channel_id (int): The ID of the channel.
            message (ModerationMessage): The message to add to the cache.
        """
        cache = self.channel_caches[channel_id]
        cache.add_message(message)

    def remove_message(self, channel_id: int, message_id: str) -> bool:
        """Remove a message from the channel's history cache.

        Args:
            channel_id (int): The ID of the channel.
            message_id (str): The ID of the message to remove.

        Returns:
            bool: True if the message was removed, False otherwise.
        """
        if channel_id not in self.channel_caches:
            return False
        
        cache = self.channel_caches[channel_id]
        return cache.remove_message(message_id)

    def get_cached_messages(self, channel_id: int) -> list[ModerationMessage]:
        """Get valid (non-expired) cached messages for a channel.

        Args:
            channel_id (int): The ID of the channel.

        Returns:
            list[ModerationMessage]: List of valid cached messages.
        """
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

        Args:
            channel_id (int): The Discord channel ID.
            limit (int): Number of messages to return.
            exclude_message_ids (Optional[set[str]]): Set of message IDs to exclude (e.g., current batch messages).

        Returns:
            list[ModerationMessage]: Up to `limit` historical messages.
        """
        if limit <= 0:
            return []

        exclude_ids = exclude_message_ids or set()

        # 1. Get cached messages
        cached = self.get_cached_messages(channel_id)
        cached_valid = [m for m in cached if str(m.message_id) not in exclude_ids]

        # 2. If cached messages are sufficient, return them
        if len(cached_valid) >= limit:
            return cached_valid[-limit:]

        # 3. If insufficient, fetch from Discord API
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
        """Fetch messages from Discord API for a channel.

        Args:
            channel_id (int): The ID of the channel.
            limit (int): Number of messages to fetch.
            exclude_ids (set[str]): Set of message IDs to exclude.

        Returns:
            list[ModerationMessage]: List of fetched messages.
        """
        if not self.bot or limit <= 0:
            return []

        try:
            channel = self.bot.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                logger.debug("Channel %s not found or not a text channel", channel_id)
                return []

            fetch_count = min(limit * 2, self.api_fetch_limit)
            messages = []

            now_utc = datetime.now(timezone.utc)
            max_age_cutoff: Optional[datetime] = None
            if self.cache_ttl_seconds > 0:
                max_age_cutoff = now_utc - timedelta(seconds=self.cache_ttl_seconds)

            async for discord_msg in channel.history(limit=fetch_count):
                if str(discord_msg.id) in exclude_ids:
                    continue
                
                # Skip bot messages (those are captured via on_message)
                if discord_msg.author.bot:
                    continue
                
                created_at = discord_msg.created_at
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                if max_age_cutoff and created_at < max_age_cutoff:
                    continue

                content = (discord_msg.clean_content or "").strip()
                embed_content = _extract_embed_content(discord_msg)
                
                # Combine text and embed content
                if embed_content:
                    if content:
                        content = f"{content}\n{embed_content}"
                    else:
                        content = embed_content
                
                images = _build_moderation_images(discord_msg)

                # Skip messages that have neither text/embed content nor image attachments
                if not content and not images:
                    continue

                mod_msg = ModerationMessage(
                    message_id=str(discord_msg.id),
                    user_id=str(discord_msg.author.id),
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
        """Clear the cache for a specific channel.

        Args:
            channel_id (int): The ID of the channel to clear.
        """
        if channel_id in self.channel_caches:
            self.channel_caches[channel_id].clear()
            logger.debug("Cleared cache for channel %s", channel_id)

    def clear_all(self) -> None:
        """Clear all cached messages."""
        self.channel_caches.clear()
        logger.info("Cleared all message caches")


# Global instance
global_history_cache_manager = GlobalHistoryCacheManager()


def initialize_cache_from_config(app_config) -> None:
    """Initialize message cache with settings from app_config.

    Args:
        app_config: Application configuration object.
    """
    global global_history_cache_manager
    try:
        if not app_config:
            return
        
        cfg_data = app_config.data if hasattr(app_config, "data") else {}
        history_cfg = cfg_data.get("history_fetching", {})
        
        if not history_cfg and hasattr(app_config, "ai_settings"):
            ai_settings = app_config.ai_settings
            # AISettings exposes a .get(...) helper; use it rather than
            # relying on dict-type compatibility.
            history_cfg = ai_settings.get("cache", {})
        
        if not history_cfg:
            return
        
        max_msgs = int(history_cfg.get("max_historical_messages_per_channel", history_cfg.get("max_messages_per_channel", 0)))
        ttl_secs = int(history_cfg.get("history_ttl_seconds", history_cfg.get("cache_ttl_seconds", 3600)))
        api_limit = int(history_cfg.get("api_fetch_limit", 100))
        
        global_history_cache_manager = GlobalHistoryCacheManager(
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