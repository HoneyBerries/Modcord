# """
# MessageBatchManager: Centralized message batching and history retrieval for moderation.

# Collects messages per-channel, tracks edits/deletions, fetches live Discord history,
# and assembles ModerationChannelBatch instances for the batch processing engine.

# Usage:
#     manager = MessageBatchManager(bot, engine)
#     await manager.add_message(channel_id, message)
#     await manager.remove_message(channel_id, message_id)
#     await manager.update_message(channel_id, message)
#     await manager.shutdown()
# """

# from __future__ import annotations

# import asyncio
# from collections import defaultdict
# from typing import Awaitable, Callable, Dict, List, Sequence

# import discord

# from modcord.configuration.app_configuration import app_config
# from modcord.database.database import get_db
# from modcord.datatypes.action_datatypes import ActionData
# from modcord.datatypes.discord_datatypes import (
#     ChannelID,
#     DiscordUsername,
#     GuildID,
#     MessageID,
#     UserID,
# )
# from modcord.datatypes.moderation_datatypes import (
#     ModerationChannelBatch,
#     ModerationMessage,
#     ModerationUser,
# )
# from modcord.history.discord_history_fetcher import DiscordHistoryFetcher
# from modcord.moderation import moderation_helper
# from modcord.util.logger import get_logger

# logger = get_logger("message_batch_manager")

# # Type alias for the batch processing engine callback
# BatchProcessingEngine = Callable[[List[ModerationChannelBatch]], Awaitable[None]]


# class MessageBatchManager:
#     """
#     Manages per-channel message batches for moderation.

#     All dependencies (bot instance, batch processing engine) are required at construction.
#     The manager collects messages, groups them by user with Discord context, fetches
#     channel history, and invokes the batch processing engine at configured intervals.

#     Attributes:
#         _bot: The Discord bot instance for API access.
#         _engine: Async callback invoked with assembled ModerationChannelBatch list.
#     """

#     def __init__(self, bot: discord.Bot, engine: BatchProcessingEngine) -> None:
#         """
#         Initialize the MessageBatchManager.

#         Args:
#             bot: Discord bot instance for channel/member lookups.
#             engine: Async function to process assembled moderation batches.
#         """
#         self._bot: discord.Bot = bot
#         self._engine: BatchProcessingEngine = engine
#         self._history_fetcher: DiscordHistoryFetcher = DiscordHistoryFetcher(bot)
#         self._batches: Dict[ChannelID, List[ModerationMessage]] = defaultdict(list)
#         self._lock: asyncio.Lock = asyncio.Lock()
#         self._timer: asyncio.Task[None] | None = None

#     # ------------------------------------------------------------------
#     # Public message operations
#     # ------------------------------------------------------------------

#     async def add_message(self, channel_id: ChannelID, message: ModerationMessage) -> None:
#         """
#         Queue a message for moderation in the given channel.

#         Args:
#             channel_id: Discord channel ID.
#             message: The ModerationMessage to queue.
#         """
#         async with self._lock:
#             self._batches[channel_id].append(message)
#             logger.debug(
#                 "Queued message %s for channel %s (batch size: %d)",
#                 message.message_id,
#                 channel_id,
#                 len(self._batches[channel_id]),
#             )
#             self._ensure_timer_running()

#     async def remove_message(self, channel_id: ChannelID, message_id: MessageID) -> None:
#         """
#         Remove a message from the pending batch (e.g., after deletion).

#         Args:
#             channel_id: Discord channel ID.
#             message_id: ID of the message to remove.
#         """
#         async with self._lock:
#             bucket = self._batches.get(channel_id)
#             if not bucket:
#                 return
#             original_len = len(bucket)
#             bucket[:] = [m for m in bucket if m.message_id != message_id]
#             if len(bucket) < original_len:
#                 logger.debug("Removed message %s from channel %s batch", message_id, channel_id)

#     async def update_message(self, channel_id: ChannelID, message: ModerationMessage) -> None:
#         """
#         Update a message in the batch (e.g., after edit).

#         Args:
#             channel_id: Discord channel ID.
#             message: The updated ModerationMessage.
#         """
#         async with self._lock:
#             bucket = self._batches.get(channel_id)
#             if not bucket:
#                 return
#             for idx, existing in enumerate(bucket):
#                 if existing.message_id == message.message_id:
#                     bucket[idx] = message
#                     logger.debug("Updated message %s in channel %s batch", message.message_id, channel_id)
#                     break

#     async def shutdown(self) -> None:
#         """Stop batching and clear all pending state."""
#         if self._timer and not self._timer.done():
#             self._timer.cancel()
#             try:
#                 await self._timer
#             except asyncio.CancelledError:
#                 pass
#         self._timer = None
#         async with self._lock:
#             self._batches.clear()
#         logger.info("MessageBatchManager shutdown complete")

#     # ------------------------------------------------------------------
#     # Timer and batch assembly
#     # ------------------------------------------------------------------

#     def _ensure_timer_running(self) -> None:
#         """Start the batch timer if not already running."""
#         if self._timer is None or self._timer.done():
#             self._timer = asyncio.create_task(self._batch_timer_task())
#             logger.debug("Started batch timer")

#     async def _batch_timer_task(self) -> None:
#         """Wait for the batch interval, then assemble and process batches."""
#         interval = app_config.ai_settings.moderation_batch_seconds
#         logger.debug("Batch timer sleeping for %s seconds", interval)
#         await asyncio.sleep(interval)

#         async with self._lock:
#             pending = {cid: list(msgs) for cid, msgs in self._batches.items() if msgs}
#             self._batches.clear()

#         if not pending:
#             logger.debug("Batch timer fired but no pending messages")
#             return

#         channel_batches = await self._assemble_batches(pending)
#         if channel_batches:
#             try:
#                 await self._engine(channel_batches)
#             except Exception:
#                 logger.exception("Exception while processing moderation batches")

#         self._timer = None

#     async def _assemble_batches(
#         self, pending: Dict[ChannelID, List[ModerationMessage]]
#     ) -> List[ModerationChannelBatch]:
#         """
#         Assemble ModerationChannelBatch objects from pending messages.

#         Args:
#             pending: Mapping of channel IDs to lists of messages.

#         Returns:
#             List of ModerationChannelBatch objects ready for processing.
#         """
#         batches: List[ModerationChannelBatch] = []

#         for channel_id, messages in pending.items():
#             channel = self._bot.get_channel(channel_id.to_int())
#             if not isinstance(channel, discord.abc.GuildChannel):
#                 logger.warning("Channel %s not found or not a guild channel", channel_id)
#                 continue

#             users = await self._group_messages_by_user(messages, channel)
#             exclude_ids = {m.message_id for m in messages}
#             history_messages = await self._history_fetcher.fetch_history_context(channel_id, exclude_ids)
#             history_users = await self._group_messages_by_user(history_messages, channel) if history_messages else []

#             logger.debug(
#                 "Prepared batch for channel %s: %d users, %d history users",
#                 channel_id,
#                 len(users),
#                 len(history_users),
#             )

#             batches.append(
#                 ModerationChannelBatch(
#                     channel_id=channel_id,
#                     channel_name=self._get_channel_name(channel),
#                     users=users,
#                     history_users=history_users,
#                 )
#             )

#         return batches

#     def _get_channel_name(self, channel: discord.abc.GuildChannel) -> str:
#         """
#         Get the name of a Discord channel.

#         Args:
#             channel: The Discord channel object.

#         Returns:
#             The channel name.

#         Raises:
#             ValueError: If the channel has no valid name.
#         """
#         name = getattr(channel, "name")
#         if not isinstance(name, str) or not name:
#             raise ValueError(f"Channel name missing for channel {channel.id}")
#         return name

#     # ------------------------------------------------------------------
#     # User grouping
#     # ------------------------------------------------------------------

#     async def _group_messages_by_user(
#         self, messages: Sequence[ModerationMessage], channel: discord.abc.GuildChannel
#     ) -> List[ModerationUser]:
#         """
#         Group messages by user and enrich with Discord context.

#         Args:
#             messages: Messages to group.
#             channel: Discord channel for guild/member lookups.

#         Returns:
#             List of ModerationUser objects sorted by first message appearance.

#         Raises:
#             ValueError: If guild, member, or join date is missing.
#         """
#         user_msgs: Dict[UserID, List[ModerationMessage]] = defaultdict(list)
#         first_seen: Dict[UserID, int] = {}

#         for idx, msg in enumerate(messages):
#             uid = msg.user_id
#             if uid not in first_seen:
#                 first_seen[uid] = idx
#             user_msgs[uid].append(msg)

#         guild = channel.guild
#         if guild is None:
#             raise ValueError(f"Guild not found for channel {channel.id}")
#         guild_id = GuildID(guild.id)
#         lookback = app_config.ai_settings.past_actions_lookback_minutes

#         users: List[ModerationUser] = []
#         for uid, msgs in user_msgs.items():
#             member = guild.get_member(uid.to_int())
#             if member is None:
#                 raise ValueError(f"Member {uid} not found in guild {guild.id}")
#             if member.joined_at is None:
#                 raise ValueError(f"Join date missing for member {uid} in guild {guild.id}")

#             past_actions: List[ActionData] = await get_db().get_past_actions(guild_id, uid, lookback)

#             users.append(
#                 ModerationUser(
#                     user_id=uid,
#                     username=DiscordUsername.from_user(member),
#                     join_date=member.joined_at,
#                     discord_member=member,
#                     discord_guild=guild,
#                     roles=[role.name for role in member.roles],
#                     messages=list(msgs),
#                     past_actions=past_actions,
#                 )
#             )

#         users.sort(key=lambda u: first_seen[u.user_id])
#         return users


# # Global singleton instance
# _message_batch_manager: MessageBatchManager | None = None


# def get_message_batch_manager(
#     bot: discord.Bot | None = None,
#     engine: BatchProcessingEngine | None = None,
# ) -> MessageBatchManager | None:
#     """
#     Get or create the global MessageBatchManager singleton.

#     Args:
#         bot: Discord bot instance (required on first call).
#         engine: Async function to process assembled moderation batches (required on first call).

#     Returns:
#         MessageBatchManager instance, or None if not yet initialized and args not provided.
#     """
#     global _message_batch_manager
#     if _message_batch_manager is None:
#         if bot is None or engine is None:
#             return None
#         _message_batch_manager = MessageBatchManager(bot, engine)
#     return _message_batch_manager