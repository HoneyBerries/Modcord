"""Scheduler for periodic synchronization of channel guidelines across all guilds.

This module handles the background task for:
- Periodically syncing channel guidelines for all connected guilds
- Managing the async task lifecycle (start/stop)
- Integration with app_config for configurable sync intervals
"""

from __future__ import annotations

import asyncio

import discord

from modcord.configuration.app_configuration import app_config
from modcord.moderation.channel_guidelines_injection_engine import channel_guidelines_injection_engine
from modcord.util.logger import get_logger

logger = get_logger("guidelines_sync_scheduler")


class GuidelinesSyncScheduler:
    """
    Scheduler for periodic synchronization of channel guidelines across all guilds.
    
    This scheduler runs a background task that periodically syncs channel guidelines
    for all guilds the bot is connected to. The sync interval is configurable
    via app_config.
    
    Methods:
        sync_all_guilds: Sync guidelines for all channels in all connected guilds.
        run_periodic_sync: Run the continuous sync loop.
        start_periodic_task: Start the background sync task.
        stop_periodic_task: Stop the background sync task.
        shutdown: Clean shutdown of the scheduler.
    """

    def __init__(self) -> None:
        """Initialize the guidelines sync scheduler."""
        self._sync_task: asyncio.Task | None = None
        self._bot: discord.Bot | None = None
        logger.info("[GUIDELINES SYNC SCHEDULER] Guidelines sync scheduler initialized")

    async def sync_all_guilds(self, bot: discord.Bot) -> None:
        """
        Sync cached guidelines for all guilds the bot is connected to.
        
        Iterates through all guilds and syncs channel guidelines using the
        channel guidelines injection engine. Individual guild errors are logged
        but don't stop the process.
        
        Args:
            bot (discord.Bot): The Discord bot instance providing guild access.
        """
        logger.debug("[GUIDELINES SYNC SCHEDULER] Syncing guidelines cache for %d guilds", len(bot.guilds))
        for guild in bot.guilds:
            try:
                await channel_guidelines_injection_engine.sync_all_channel_guidelines(guild)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("[GUIDELINES SYNC SCHEDULER] Failed to sync guidelines for guild %s: %s", guild.name, exc)

    async def run_periodic_sync(
        self,
        bot: discord.Bot,
        interval_seconds: float = 600.0,
    ) -> None:
        """
        Continuously sync guidelines cache on a fixed interval.
        
        Runs an infinite loop that syncs all guilds' channel guidelines, then sleeps
        for the specified interval before syncing again.
        
        Args:
            bot (discord.Bot): Discord client instance whose guilds require periodic sync.
            interval_seconds (float): Delay between successive sync runs. Defaults to 600.0 (10 minutes).
        
        Raises:
            asyncio.CancelledError: Propagated when the task is cancelled for shutdown.
        """
        self._bot = bot
        logger.info(
            "[GUIDELINES SYNC SCHEDULER] Starting periodic guidelines sync (interval=%.1fs) for %d guilds",
            interval_seconds,
            len(bot.guilds),
        )
        try:
            while True:
                try:
                    await self.sync_all_guilds(bot)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error("[GUIDELINES SYNC SCHEDULER] Unexpected error during guidelines sync: %s", exc)
                await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            logger.info("[GUIDELINES SYNC SCHEDULER] Periodic guidelines sync cancelled")
            raise

    async def start_periodic_task(self, bot: discord.Bot, interval_seconds: float | None = None) -> None:
        """
        Start the periodic guidelines sync background task.
        
        Creates and runs the periodic sync task if one isn't already running.
        If interval_seconds is not provided, reads the interval from app_config.
        
        Args:
            bot (discord.Bot): Discord client instance to use for syncing.
            interval_seconds (float | None): Sync interval in seconds. If None,
                reads from app_config.guidelines_sync_interval.
        """
        if interval_seconds is None:
            interval_seconds = app_config.guidelines_sync_interval

        if self._sync_task and not self._sync_task.done():
            logger.warning("[GUIDELINES SYNC SCHEDULER] Periodic sync task already running")
            return

        self._sync_task = asyncio.create_task(
            self.run_periodic_sync(bot, interval_seconds=interval_seconds)
        )
        logger.info("[GUIDELINES SYNC SCHEDULER] Started periodic guidelines sync task")

    async def stop_periodic_task(self) -> None:
        """
        Stop the periodic sync task if it's currently running.
        
        Cancels the background sync task and waits for it to complete cleanup.
        Safe to call even if no task is running.
        """
        if self._sync_task and not self._sync_task.done():
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
            logger.info("[GUIDELINES SYNC SCHEDULER] Stopped periodic guidelines sync task")

    async def shutdown(self) -> None:
        """
        Cleanly shutdown the guidelines sync scheduler.
        
        Stops the periodic sync task if running and cleans up resources.
        This method should be called during bot shutdown to ensure proper cleanup.
        """
        await self.stop_periodic_task()
        self._bot = None
        self._sync_task = None
        logger.info("[GUIDELINES SYNC SCHEDULER] Guidelines sync scheduler shutdown complete")


# Global instance
guidelines_sync_scheduler = GuidelinesSyncScheduler()
