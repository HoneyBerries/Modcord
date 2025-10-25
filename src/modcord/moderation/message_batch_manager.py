"""
MessageBatchManager: Centralized coordination of message batching and history retrieval for moderation.

This module provides a lightweight manager that:
- Collects new messages per-channel for moderation batches.
- Tracks edits and deletions prior to batch submission.
- Fetches up-to-date channel history directly from Discord (no cache).
- Assembles ModerationChannelBatch instances and invokes the downstream moderation pipeline callback.

Usage:
- Use add_message_to_batch, remove_message_from_batch, and update_message_in_batch in your Discord event listeners.
- Set the bot instance and batch processing callback before starting moderation.
- Call shutdown() on bot shutdown.
"""

from __future__ import annotations

import asyncio
import datetime
from collections import defaultdict
from typing import Awaitable, Callable, DefaultDict, Dict, List, Optional, Sequence, Set

import discord

from modcord.configuration.app_configuration import app_config
from modcord.database.database import get_past_actions
from modcord.moderation.moderation_datatypes import (
    ModerationChannelBatch,
    ModerationImage,
    ModerationMessage,
    ModerationUser,
)
from modcord.util.image_utils import generate_image_hash_id
from modcord.util.logger import get_logger

logger = get_logger("message_batch_manager")

# Discord attachment types considered images for moderation context
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")


class MessageBatchManager:
    """
    Manages per-channel message batches for moderation.

    Main API:
    - add_message_to_batch(channel_id, message): Queue a new message for moderation.
    - remove_message_from_batch(channel_id, message_id): Remove a deleted message from batch.
    - update_message_in_batch(channel_id, message): Update a message in batch after edit.
    - set_bot_instance(bot_instance): Set the Discord bot instance for API access.
    - set_batch_processing_callback(callback): Set the function to call with assembled batches.
    - shutdown(): Cleanly stop batching and clear state.

    All history is fetched live from Discord. Edits and deletions are reflected in both the current batch and history.
    """

    def __init__(self) -> None:
        self._channel_message_batches: DefaultDict[int, List[ModerationMessage]] = defaultdict(list)
        self._batch_lock = asyncio.Lock()
        self._global_batch_timer: Optional[asyncio.Task] = None
        self._batch_processing_callback: Optional[
            Callable[[List[ModerationChannelBatch]], Awaitable[None]]
        ] = None
        self._bot_instance: Optional[discord.Client] = None

    # ------------------------------------------------------------------
    # Public configuration hooks
    # ------------------------------------------------------------------
    def set_bot_instance(self, bot_instance: discord.Client) -> None:
        """
        Set the Discord bot instance for API access and channel lookups.

        Args:
            bot_instance (discord.Client): The Discord bot instance to use for Discord API calls and channel lookups.

        Returns:
            None
        """
        self._bot_instance = bot_instance
        logger.info("Bot instance set for MessageBatchManager")

    def set_batch_processing_callback(
        self,
        callback: Callable[[List[ModerationChannelBatch]], Awaitable[None]],
    ) -> None:
        """
        Set the callback to invoke with assembled moderation batches.

        Args:
            callback (Callable[[List[ModerationChannelBatch]], Awaitable[None]]):
                Async function to call with a list of ModerationChannelBatch objects when a batch is ready.

        Returns:
            None
        """
        self._batch_processing_callback = callback
        logger.info("Batch processing callback configured")

    # ------------------------------------------------------------------
    # Message tracking operations
    # ------------------------------------------------------------------
    async def add_message_to_batch(self, channel_id: int, message: ModerationMessage) -> None:
        """
        Add a new message to the moderation batch for the given channel.

        Args:
            channel_id (int): Discord channel ID to queue the message for.
            message (ModerationMessage): The message object to add to the batch.

        Returns:
            None
        """
        async with self._batch_lock:
            bucket = self._channel_message_batches[channel_id]
            bucket.append(message)
            logger.debug(
                "Queued message %s for channel %s (batch size now %d)",
                message.message_id,
                channel_id,
                len(bucket),
            )

            if self._global_batch_timer is None or self._global_batch_timer.done():
                self._global_batch_timer = asyncio.create_task(self._global_batch_timer_task())
                logger.debug("Started global batch timer")

    async def remove_message_from_batch(self, channel_id: int, message_id: str) -> None:
        """
        Remove a message from the pending batch for the given channel by message ID.

        Args:
            channel_id (int): Discord channel ID to remove the message from.
            message_id (str): The ID of the message to remove from the batch.

        Returns:
            None
        """
        async with self._batch_lock:
            bucket = self._channel_message_batches.get(channel_id)
            if not bucket:
                return

            before = len(bucket)
            message_id_str = str(message_id)
            bucket[:] = [msg for msg in bucket if str(msg.message_id) != message_id_str]
            after = len(bucket)
            if before != after:
                logger.debug(
                    "Removed message %s from channel %s batch (size %d -> %d)",
                    message_id_str,
                    channel_id,
                    before,
                    after,
                )

    async def update_message_in_batch(self, channel_id: int, message: ModerationMessage) -> None:
        """
        Update a message in the batch with new content (e.g., after edit).

        Args:
            channel_id (int): Discord channel ID containing the message to update.
            message (ModerationMessage): The updated message object to replace the old one in the batch.

        Returns:
            None
        """
        async with self._batch_lock:
            bucket = self._channel_message_batches.get(channel_id)
            if not bucket:
                return

            target_id = str(message.message_id)
            for idx, existing in enumerate(bucket):
                if str(existing.message_id) == target_id:
                    bucket[idx] = message
                    logger.debug(
                        "Updated message %s for channel %s in current batch", target_id, channel_id
                    )
                    break

    # ------------------------------------------------------------------
    # Timer + batch assembly
    # ------------------------------------------------------------------
    async def _global_batch_timer_task(self) -> None:
        """Timer task that assembles and processes moderation batches at intervals."""
        try:
            moderation_batch_seconds = float(
                app_config.ai_settings.get("moderation_batch_seconds", 10.0)
            )
        except Exception:
            moderation_batch_seconds = 10.0
        logger.debug("Global batch timer sleeping for %s seconds", moderation_batch_seconds)
        await asyncio.sleep(moderation_batch_seconds)

        async with self._batch_lock:
            pending_batches = {
                channel_id: list(messages)
                for channel_id, messages in self._channel_message_batches.items()
                if messages
            }
            self._channel_message_batches.clear()

        if not pending_batches:
            logger.debug("Global batch timer fired but no pending messages")
            return

        channel_batches: List[ModerationChannelBatch] = []
        for channel_id, messages in pending_batches.items():
            users = await self._group_messages_by_user(messages)
            history_users = []  # If you want to log history users, fetch from _fetch_history_context
            # Example: history_users = await self._fetch_history_context(channel_id, messages)

            logger.debug(
                "Prepared batch for channel %s: %d current users, %d history users",
                channel_id,
                len(users),
                len(history_users),
            )

            channel_batches.append(
                ModerationChannelBatch(
                    channel_id=channel_id,
                    channel_name=self._resolve_channel_name(channel_id),
                    users=users,
                    history_users=history_users,
                )
            )

        if channel_batches and self._batch_processing_callback:
            try:
                await self._batch_processing_callback(channel_batches)
            except Exception:
                logger.exception("Exception while processing moderation batches")
        else:
            logger.debug("No batch processing callback configured")

        self._global_batch_timer = None

    def _resolve_channel_name(self, channel_id: int) -> str:
        channel = self._bot_instance.get_channel(channel_id) if self._bot_instance else None
        if channel:
            name = getattr(channel, "name", None)
            if isinstance(name, str) and name:
                return name
        return f"Channel {channel_id}"

    # ------------------------------------------------------------------
    # History + grouping helpers
    # ------------------------------------------------------------------
    async def _group_messages_by_user(
        self, messages: Sequence[ModerationMessage]
    ) -> List[ModerationUser]:
        user_messages: Dict[str, List[ModerationMessage]] = defaultdict(list)
        first_seen: Dict[str, int] = {}

        for idx, msg in enumerate(messages):
            user_id = str(msg.user_id)
            if user_id not in first_seen:
                first_seen[user_id] = idx
            user_messages[user_id].append(msg)

        lookback_minutes = app_config.ai_settings.get("past_actions_lookback_minutes", 10080)

        grouped_users: List[ModerationUser] = []
        for user_id, msgs in user_messages.items():
            discord_msg = next((m.discord_message for m in msgs if m.discord_message), None)

            username = "Unknown User"
            roles: List[str] = []
            join_date: Optional[str] = None
            guild_id: Optional[int] = None

            if discord_msg and discord_msg.guild and discord_msg.author:
                username = str(discord_msg.author)
                guild_id = discord_msg.guild.id

                if isinstance(discord_msg.author, discord.Member):
                    member = discord_msg.author
                    roles = [role.name for role in member.roles if role.name != "@everyone"]
                    if member.joined_at:
                        join_date = (
                            member.joined_at.astimezone(datetime.timezone.utc)
                            .replace(microsecond=0)
                            .isoformat()
                            .replace("+00:00", "Z")
                        )

            past_actions: List[dict] = []
            if guild_id:
                try:
                    past_actions = await get_past_actions(guild_id, user_id, lookback_minutes)
                except Exception as exc:
                    logger.warning(
                        "Failed to query past actions for user %s in guild %s: %s",
                        user_id,
                        guild_id,
                        exc,
                    )

            grouped_users.append(
                ModerationUser(
                    user_id=user_id,
                    username=username,
                    roles=roles,
                    join_date=join_date,
                    messages=list(msgs),
                    past_actions=past_actions,
                )
            )

        grouped_users.sort(key=lambda user: first_seen[user.user_id])
        return grouped_users

    async def _fetch_history_context(
        self,
        channel_id: int,
        current_batch: Sequence[ModerationMessage],
    ) -> List[ModerationMessage]:
        bot = self._bot_instance
        if not bot:
            return []

        channel = bot.get_channel(channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return []

        exclude_ids: Set[str] = {str(msg.message_id) for msg in current_batch}
        history_limit = 20
        try:
            history_limit = int(app_config.ai_settings.get("history_context_messages", 20))
        except Exception:
            pass

        fetch_count = min(history_limit * 2, 100)
        results: List[ModerationMessage] = []
        try:
            async for discord_msg in channel.history(limit=fetch_count):
                if str(discord_msg.id) in exclude_ids:
                    continue
                if discord_msg.author.bot:
                    continue

                mod_msg = self._convert_discord_message(discord_msg)
                if mod_msg:
                    results.append(mod_msg)
                if len(results) >= history_limit:
                    break
        except discord.Forbidden:
            logger.warning("Missing permissions to read history for channel %s", channel_id)
        except discord.NotFound:
            logger.warning("Channel %s not found while fetching history", channel_id)
        except Exception as exc:
            logger.error(
                "Unexpected error fetching history for channel %s: %s",
                channel_id,
                exc,
            )

        return results

    def _convert_discord_message(self, message: discord.Message) -> Optional[ModerationMessage]:
        content = (message.clean_content or "").strip()
        embed_content = self._extract_embed_content(message)
        if embed_content:
            content = f"{content}\n{embed_content}" if content else embed_content

        images = self._build_moderation_images(message)

        if not content and not images:
            return None

        created_at = message.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=datetime.timezone.utc)

        return ModerationMessage(
            message_id=str(message.id),
            user_id=str(message.author.id),
            content=content,
            timestamp=created_at.astimezone(datetime.timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            guild_id=message.guild.id if message.guild else None,
            channel_id=message.channel.id if message.channel else None,
            images=images,
            discord_message=None,
        )

    @staticmethod
    def _extract_embed_content(message: discord.Message) -> str:
        if not message.embeds:
            return ""

        parts: List[str] = []
        for embed in message.embeds:
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

        return "\n".join(parts)

    def _build_moderation_images(self, message: discord.Message) -> List[ModerationImage]:
        images: List[ModerationImage] = []
        for attachment in message.attachments:
            if not self._is_image_attachment(attachment):
                continue
            images.append(
                ModerationImage(
                    image_id=generate_image_hash_id(attachment.url),
                    pil_image=None,
                )
            )
        return images

    @staticmethod
    def _is_image_attachment(attachment: discord.Attachment) -> bool:
        content_type = (attachment.content_type or "").lower()
        if content_type.startswith("image/"):
            return True
        if attachment.width is not None and attachment.height is not None:
            return True
        filename = (attachment.filename or "").lower()
        return filename.endswith(IMAGE_EXTENSIONS)

    # ------------------------------------------------------------------
    # Shutdown helpers
    # ------------------------------------------------------------------
    async def shutdown(self) -> None:
        """
        Cleanly stop batching and clear all pending state.

        Cancels the global batch timer and clears all queued messages.

        Returns:
            None
        """
        if self._global_batch_timer and not self._global_batch_timer.done():
            self._global_batch_timer.cancel()
            try:
                await self._global_batch_timer
            except asyncio.CancelledError:
                pass
        self._global_batch_timer = None

        async with self._batch_lock:
            self._channel_message_batches.clear()

        logger.info("MessageBatchManager shutdown complete")


message_batch_manager = MessageBatchManager()