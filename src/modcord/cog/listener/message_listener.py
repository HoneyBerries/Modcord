"""Message listener Cog for Modcord.

This cog has exactly ONE responsibility: listen to Discord message events and
forward qualifying messages to the ModerationQueueService.

All batching, conversion, enrichment, and AI moderation logic lives in the
service layer — NOT here.
"""

import discord
from discord.ext import commands

from modcord.services.message_processing_service import MessageProcessingService
from modcord.services.moderation_queue_service import ModerationQueueService
from modcord.util.discord import discord_utils
from modcord.util.logger import get_logger

logger = get_logger("message_listener_cog")


class MessageListenerCog(commands.Cog):
    """
    Thin event listener that forwards messages to the queue service.

    Parameters
    ----------
    bot:
        Discord bot instance.
    queue_service:
        Receives enqueued messages and manages per-channel workers.
    processing_service:
        Called by the queue worker to convert/enrich/dispatch a batch.
    """

    def __init__(
        self,
        bot: discord.Bot,
        queue_service: ModerationQueueService,
        processing_service: MessageProcessingService,
    ) -> None:
        self.bot = bot
        self._queue_service = queue_service
        self._processing_service = processing_service
        logger.info("[MESSAGE LISTENER] Message listener cog loaded")

    # ------------------------------------------------------------------
    # Event handlers — keep these as small as possible
    # ------------------------------------------------------------------

    @commands.Cog.listener(name="on_message")
    async def on_message(self, message: discord.Message) -> None:
        """Filter and enqueue qualifying messages for moderation."""
        if not discord_utils.should_process_message(message):
            return

        logger.debug(
            "Received message from %s: %s",
            message.author,
            (message.clean_content or "[no text]")[:80],
        )

        await self._queue_service.enqueue_message(message, self._processing_service)



def setup(
    bot: discord.Bot,
    queue_service: ModerationQueueService,
    processing_service: MessageProcessingService) -> None:
    """Register the MessageListenerCog with the bot."""
    bot.add_cog(MessageListenerCog(bot, queue_service, processing_service))
