"""Generic scheduler for periodic per-guild sync tasks.

Provides a reusable async task runner that iterates all guilds on a fixed interval,
calling a user-supplied coroutine for each guild. Handles lifecycle (start/stop/shutdown)
and standard error handling.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

import discord

from modcord.util.logger import get_logger

logger = get_logger("sync_scheduler")


class GenericSyncScheduler:
    """
    Reusable scheduler for periodic per-guild sync operations.

    Args:
        name: Human-readable name for logging (e.g., "rules", "guidelines").
        per_guild_coro: Async callable that accepts a single `discord.Guild` argument.
        get_interval: Callable returning the interval in seconds (called at start).
    """

    def __init__(
        self,
        name: str,
        per_guild_coro: Callable[[discord.Guild], Awaitable[Any]],
        get_interval: Callable[[], float],
    ) -> None:
        self._name = name
        self._per_guild_coro = per_guild_coro
        self._get_interval = get_interval
        self._task: asyncio.Task | None = None
        self._bot: discord.Bot | None = None


    async def _sync_all_guilds(self, bot: discord.Bot) -> None:
        """Iterate bot.guilds and call per_guild_coro for each."""
        for guild in bot.guilds:
            try:
                await self._per_guild_coro(guild)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("[%s] Failed to sync guild %s: %s", self._name, guild.name, exc)


    async def _run_loop(self, bot: discord.Bot, interval: float) -> None:
        """Infinite loop: sync all guilds, sleep, repeat."""
        logger.info("[%s] Starting periodic sync (interval=%.1fs) for %d guilds", self._name, interval, len(bot.guilds))
        try:
            while True:
                try:
                    await self._sync_all_guilds(bot)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error("[%s] Unexpected error during sync: %s", self._name, exc)
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("[%s] Periodic sync cancelled", self._name)
            raise


    def start(self, bot: discord.Bot) -> None:
        """Start the background sync task if not already running."""
        if self._task and not self._task.done():
            logger.warning("[%s] Sync task already running", self._name)
            return
        self._bot = bot
        interval = self._get_interval()
        logger.info("[%s] Creating sync task with interval %.1fs", self._name, interval)
        self._task = asyncio.create_task(self._run_loop(bot, interval))


    async def shutdown(self) -> None:
        """Full shutdown: stop task and clear references."""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("[%s] Scheduler shutdown complete", self._name)
