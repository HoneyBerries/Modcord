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
from typing import Awaitable, Callable, DefaultDict, Dict, List, Sequence, Set

import discord

from modcord.configuration.app_configuration import app_config
from modcord.database.database import get_past_actions
from modcord.history.discord_history_fetcher import DiscordHistoryFetcher
from modcord.moderation.moderation_datatypes import (
    ModerationChannelBatch,
    ModerationMessage,
    ModerationUser,
)
from modcord.util.logger import get_logger

logger = get_logger("message_batch_manager")


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
        self._global_batch_timer: asyncio.Task | None = None
        self._batch_processing_callback: (
            Callable[[List[ModerationChannelBatch]], Awaitable[None]] | None
        ) = None
        self._bot_instance: discord.Bot | None = None
        self._history_fetcher: DiscordHistoryFetcher | None = self._bot_instance

    # ------------------------------------------------------------------
    # Public configuration hooks
    # ------------------------------------------------------------------
    def set_bot_instance(self, bot_instance: discord.Bot) -> None:
        """
        Set the Discord bot instance for API access and channel lookups.

        Args:
            bot_instance (discord.Bot): The Discord bot instance to use for Discord API calls and channel lookups.

        Returns:
            None
        """
        self._bot_instance = bot_instance
        self._history_fetcher = DiscordHistoryFetcher(bot_instance)
        logger.info("[MESSAGE BATCH MANAGER] Bot instance set for MessageBatchManager")

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
        logger.info("[MESSAGE BATCH MANAGER] Batch processing callback configured")

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
                "[MESSAGE BATCH MANAGER] Queued message %s for channel %s (batch size now %d)",
                message.message_id,
                channel_id,
                len(bucket),
            )

            if self._global_batch_timer is None or self._global_batch_timer.done():
                self._global_batch_timer = asyncio.create_task(self._global_batch_timer_task())
                logger.debug("[MESSAGE BATCH MANAGER] Started global batch timer")

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
                    "[MESSAGE BATCH MANAGER] Removed message %s from channel %s batch (size %d -> %d)",
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
                        "[MESSAGE BATCH MANAGER] Updated message %s for channel %s in current batch", target_id, channel_id
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
        logger.debug("[MESSAGE BATCH MANAGER] Global batch timer sleeping for %s seconds", moderation_batch_seconds)
        await asyncio.sleep(moderation_batch_seconds)

        async with self._batch_lock:
            pending_batches = {
                channel_id: list(messages)
                for channel_id, messages in self._channel_message_batches.items()
                if messages
            }
            self._channel_message_batches.clear()

        if not pending_batches:
            logger.debug("[MESSAGE BATCH MANAGER] Global batch timer fired but no pending messages")
            return

        channel_batches: List[ModerationChannelBatch] = []
        for channel_id, messages in pending_batches.items():
            users = await self._group_messages_by_user(messages)
            
            # Fetch fresh history from Discord
            history_messages: List[ModerationMessage] = []
            if self._history_fetcher:
                exclude_ids = {str(msg.message_id) for msg in messages}
                history_messages = await self._history_fetcher.fetch_history_context(
                    channel_id, exclude_ids
                )
            
            history_users = await self._group_messages_by_user(history_messages) if history_messages else []

            logger.debug(
                "[MESSAGE BATCH MANAGER] Prepared batch for channel %s: %d current users, %d history users",
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
                logger.exception("[MESSAGE BATCH MANAGER] Exception while processing moderation batches")
        else:
            logger.debug("[MESSAGE BATCH MANAGER] No batch processing callback configured")

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

        # Single pass through messages - cache user_id strings
        for idx, msg in enumerate(messages):
            user_id = str(msg.user_id)
            if user_id not in first_seen:
                first_seen[user_id] = idx
            user_messages[user_id].append(msg)

        lookback_minutes = app_config.ai_settings.get("past_actions_lookback_days", 7) * 24 * 60

        grouped_users: List[ModerationUser] = []
        for user_id, msgs in user_messages.items():
            # Use next() with generator for early exit - more efficient than list comprehension
            discord_msg = next((m.discord_message for m in msgs if m.discord_message), None)

            username = "Unknown User"
            roles: List[str] = []
            join_date: str | None = None
            guild_id: int | None = None

            if discord_msg and discord_msg.guild and discord_msg.author:
                username = str(discord_msg.author)
                guild_id = discord_msg.guild.id

                if isinstance(discord_msg.author, discord.Member):
                    member = discord_msg.author
                    # List comprehension is faster than generator for small lists
                    roles = [role.name for role in member.roles]
                    if member.joined_at:
                        # Cache timezone to avoid repeated attribute access
                        utc_tz = datetime.timezone.utc
                        join_date = (
                            member.joined_at.astimezone(utc_tz)
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
                        "[MESSAGE BATCH MANAGER] Failed to query past actions for user %s in guild %s: %s",
                        user_id,
                        guild_id,
                        exc,
                    )

            # Avoid redundant list() conversion - msgs is already iterable
            grouped_users.append(
                ModerationUser(
                    user_id=user_id,
                    username=username,
                    roles=roles,
                    join_date=join_date,
                    messages=msgs,  # Direct assignment instead of list(msgs)
                    past_actions=past_actions,
                )
            )

        # Sort once at the end using cached first_seen dict
        grouped_users.sort(key=lambda user: first_seen[user.user_id])
        return grouped_users

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

        logger.info("[MESSAGE BATCH MANAGER] MessageBatchManager shutdown complete")


message_batch_manager = MessageBatchManager()