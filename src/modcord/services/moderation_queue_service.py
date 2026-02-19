"""
Moderation Queue Service.

Manages a per-guild asyncio.Queue and a persistent worker task for each guild.
The cog just calls enqueue_message(); all batching/timer logic lives here.
"""

from __future__ import annotations

import asyncio
from typing import List

import discord

from modcord.configuration.app_configuration import app_config
from modcord.datatypes.discord_datatypes import GuildID
from modcord.services.message_processing_service import MessageProcessingService
from modcord.util.logger import get_logger

logger = get_logger("moderation_queue_service")


class ModerationQueueService:
    """
    Per-guild queue that batches incoming Discord messages and forwards
    them to MessageProcessingService for conversion, enrichment, and AI
    moderation.

    Design notes
    ------------
    * One asyncio.Queue per guild — all channels feed into the same queue.
    * One persistent worker coroutine per guild — started lazily on first
      message, runs forever while the bot is alive.
    * Batching is achieved by waiting ``batch_interval`` seconds after the
      FIRST message arrives before draining the rest of the queue.
    * If the worker task dies, the next message for that guild will
      transparently restart it.
    """

    def __init__(self) -> None:
        self._queues: dict[GuildID, asyncio.Queue[discord.Message]] = {}
        self._workers: dict[GuildID, asyncio.Task] = {}

    # ------------------------------------------------------
    # Public API
    # ------------------------------------------------------

    async def enqueue_message(
        self,
        message: discord.Message,
        processing_service: MessageProcessingService,
    ) -> None:
        """
        Place a message on the guild's queue.

        If no worker exists for this guild (or the previous one crashed),
        a new persistent worker is started.
        """
        if message.guild is None:
            return

        guild_id = GuildID.from_discord(message.guild)
        queue = self._get_or_create_queue(guild_id)
        await queue.put(message)

        # Start (or restart) worker if necessary
        worker = self._workers.get(guild_id)
        if worker is None or worker.done():
            self._workers[guild_id] = asyncio.create_task(
                self._guild_worker(guild_id, queue, processing_service),
                name=f"modq-worker-guild-{guild_id}",
            )
            logger.debug("Started queue worker for guild %s", guild_id)

    async def shutdown(self) -> None:
        """Cancel all worker tasks gracefully during bot shutdown."""
        for task in self._workers.values():
            if not task.done():
                task.cancel()
        if self._workers:
            await asyncio.gather(*self._workers.values(), return_exceptions=True)
        self._workers.clear()
        self._queues.clear()
        logger.info("[QUEUE SERVICE] All guild workers shut down.")

    # -------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------

    def _get_or_create_queue(self, guild_id: GuildID) -> asyncio.Queue[discord.Message]:
        if guild_id not in self._queues:
            self._queues[guild_id] = asyncio.Queue()
        return self._queues[guild_id]

    async def _guild_worker(
        self,
        guild_id: GuildID,
        queue: asyncio.Queue[discord.Message],
        processing_service: MessageProcessingService,
    ) -> None:
        """
        Persistent worker for one guild.

        Waits for the first message, sleeps for ``batch_interval`` seconds to
        let more messages accumulate, then drains the queue and forwards the
        batch to the processing service.  Messages from ALL channels in the
        guild are collected together.
        """
        logger.debug("Guild worker running for guild %s", guild_id)
        while True:
            messages: List[discord.Message] = []

            try:
                # Block until at least one message arrives
                first = await queue.get()
                messages.append(first)

                # Collect any more messages that arrive within the batch window
                interval = app_config.moderation_batch_seconds
                await asyncio.sleep(interval)
                while not queue.empty():
                    messages.append(queue.get_nowait())

            except asyncio.CancelledError:
                logger.info("Guild worker cancelled for guild %s", guild_id)
                return
            except Exception:
                logger.exception(
                    "Unexpected error collecting messages for guild %s", guild_id
                )
                continue

            if not messages:
                continue

            logger.info(
                "Guild %s: forwarding batch of %d message(s) from %d channel(s) to processing service",
                guild_id,
                len(messages),
                len({m.channel.id for m in messages}),
            )

            try:
                await processing_service.process_batch(messages)
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception(
                    "Processing service raised an exception for guild %s batch", guild_id
                )