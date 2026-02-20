"""Background scheduler cogs for Modcord.

Contains three cogs:
- RulesSyncCog      – periodically syncs server rules for every guild
- GuidelinesSyncCog – periodically syncs channel topics for every guild
- UnbanSchedulerCog – DB-polling loop that lifts temporary bans on time
"""

from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable

import discord
from discord.ext import commands, tasks

from modcord.configuration.app_configuration import app_config
from modcord.database.db_connection import db_connection
from modcord.datatypes.discord_datatypes import GuildID, ChannelID, UserID
from modcord.repositories.temporary_ban_repo import tempban_storage
from modcord.settings.guild_settings_manager import guild_settings_manager
from modcord.util.discord import collector
from modcord.util.logger import get_logger

logger = get_logger("scheduler_cog")

_UNBAN_POLL_SECONDS = 5


# ---------------------------------------------------------------------------
# Shared base for per-guild interval sync cogs
# ---------------------------------------------------------------------------

class _IntervalSyncCog(commands.Cog):
    """
    Reusable base for cogs that run a periodic per-guild async function.

    Subclasses supply:
        _name          – human-readable tag used in log messages
        _get_interval  – callable returning the configured interval in seconds
        _sync_guild    – async callable(guild) that does the real work
    """

    _name: str
    _get_interval: Callable[[], float]
    _sync_guild: Callable[[discord.Guild], Awaitable[None]]

    def __init__(self, bot: discord.Bot) -> None:
        self.bot = bot

    @tasks.loop(seconds=1)  # real interval set in on_ready
    async def _sync_task(self) -> None:
        for guild in self.bot.guilds:
            try:
                await self._sync_guild(guild)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("[%s] Failed to sync guild %s: %s", self._name, guild.name, exc)

    @_sync_task.before_loop
    async def _before_sync(self) -> None:
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        interval = self._get_interval()
        self._sync_task.change_interval(seconds=interval)
        if not self._sync_task.is_running():
            self._sync_task.start()
            logger.info("[%s] Started (interval=%.1fs)", self._name, interval)

    def cog_unload(self) -> None:
        self._sync_task.cancel()
        logger.info("[%s] Stopped", self._name)


# ---------------------------------------------------------------------------
# Rules sync
# ---------------------------------------------------------------------------

class RulesSyncCog(_IntervalSyncCog):
    """Periodically syncs server rules from rule-like channels into guild settings."""

    _name = "RULES_SYNC"
    _get_interval = staticmethod(lambda: app_config.rules_sync_interval)

    @staticmethod
    async def _sync_guild(guild: discord.Guild) -> None:
        rules_text = await collector.collect_rules(guild)
        await guild_settings_manager.update(GuildID(guild.id), rules=rules_text)


# ---------------------------------------------------------------------------
# Guidelines sync
# ---------------------------------------------------------------------------

class GuidelinesSyncCog(_IntervalSyncCog):
    """Periodically syncs channel topics into per-guild channel guidelines."""

    _name = "GUIDELINES_SYNC"
    _get_interval = staticmethod(lambda: app_config.guidelines_sync_interval)

    @staticmethod
    async def _sync_guild(guild: discord.Guild) -> None:
        guild_id = GuildID(guild.id)
        new_guidelines = {
            ChannelID(ch.id): collector.collect_channel_topic(ch)
            for ch in guild.text_channels
        }
        await guild_settings_manager.update(guild_id, channel_guidelines=new_guidelines)


# ---------------------------------------------------------------------------
# Unban scheduler  (DB-polling – persistent across restarts)
# ---------------------------------------------------------------------------

class UnbanSchedulerCog(commands.Cog):
    """
    DB-driven scheduler that lifts temporary bans when their duration expires.

    Design
    ------
    - Bans are recorded in the ``temporary_bans`` SQLite table at ban time
      with ``unban_at`` stored as a unix integer (seconds since the epoch).
    - A ``tasks.loop`` polls every ``_UNBAN_POLL_SECONDS`` seconds and
      executes every expired row it finds.
    - Because state lives in the database, bot restarts are transparent.

    Public API (used by moderation_helper)
    --------------------------------------
        await cog.schedule(guild, user_id, duration_seconds, reason=...)
        await cog.cancel(guild_id, user_id)

    Access via:
        bot.cogs["UnbanSchedulerCog"]
    """

    def __init__(self, bot: discord.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # Cog lifecycle
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if not self._poll_task.is_running():
            self._poll_task.start()
        logger.info("[UNBAN_SCHEDULER] Ready (poll interval=%ds)", _UNBAN_POLL_SECONDS)

    def cog_unload(self) -> None:
        self._poll_task.cancel()
        logger.info("[UNBAN_SCHEDULER] Stopped")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def schedule(
        self,
        guild: discord.Guild,
        user_id: UserID,
        duration_seconds: float,
        *,
        reason: str = "Ban duration expired.",
    ) -> None:
        """Persist a tempban so it survives restarts and will be lifted on time.

        Pass ``sys.maxsize`` (or any negative value) for a permanent ban —
        no DB row is written and the ban is never automatically lifted.
        """
        import sys
        if duration_seconds < 0 or duration_seconds >= sys.maxsize:
            # Permanent ban — nothing to schedule
            logger.debug(
                "[UNBAN_SCHEDULER] Permanent ban for %s in guild %s — skipping schedule",
                user_id, guild.id,
            )
            return

        unban_at = int(time.time()) + int(duration_seconds)

        async with db_connection.transaction() as conn:
            await tempban_storage.upsert(
                conn,
                guild_id=guild.id,
                user_id=str(user_id),
                unban_at=unban_at,
                reason=reason,
            )

        logger.debug(
            "[UNBAN_SCHEDULER] Scheduled unban for %s in guild %s at unix=%d",
            user_id, guild.id, unban_at,
        )

    async def cancel(self, guild_id: int, user_id: UserID) -> bool:
        """Remove a pending unban. Returns True if a row was deleted."""
        async with db_connection.transaction() as conn:
            exists = await tempban_storage.exists(conn, guild_id, str(user_id))
            if not exists:
                return False
            await tempban_storage.delete(conn, guild_id, str(user_id))

        logger.debug("[UNBAN_SCHEDULER] Cancelled unban for %s in guild %s", user_id, guild_id)
        return True

    # ------------------------------------------------------------------
    # Polling loop
    # ------------------------------------------------------------------

    @tasks.loop(seconds=_UNBAN_POLL_SECONDS)
    async def _poll_task(self) -> None:
        now = int(time.time())

        async with db_connection.read() as conn:
            expired = await tempban_storage.get_expired(conn, now)

        for record in expired:
            guild = self.bot.get_guild(record.guild_id)
            if guild is None:
                logger.warning(
                    "[UNBAN_SCHEDULER] Guild %s not found – skipping %s",
                    record.guild_id, record.user_id,
                )
                continue

            try:
                await self._lift_ban(guild, UserID(record.user_id), record.reason)
            except Exception as exc:
                logger.error("[UNBAN_SCHEDULER] Failed to unban %s: %s", record.user_id, exc)
                continue  # leave the row; will retry next poll

            # Remove the row only after a successful unban
            async with db_connection.transaction() as conn:
                await tempban_storage.delete(conn, record.guild_id, record.user_id)

    @_poll_task.before_loop
    async def _before_poll(self) -> None:
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _lift_ban(
        self,
        guild: discord.Guild,
        user_id: UserID,
        reason: str,
    ) -> None:
        """Unban the user from the guild."""
        try:
            await guild.unban(discord.Object(id=int(user_id)), reason=reason)
            logger.debug("[UNBAN_SCHEDULER] Unbanned %s in guild %s", user_id, guild.id)
        except discord.NotFound:
            logger.warning(
                "[UNBAN_SCHEDULER] %s not found in ban list for guild %s – already unbanned?",
                user_id, guild.id,
            )


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def setup(bot: discord.Bot) -> None:
    bot.add_cog(RulesSyncCog(bot))
    bot.add_cog(GuidelinesSyncCog(bot))
    bot.add_cog(UnbanSchedulerCog(bot))
