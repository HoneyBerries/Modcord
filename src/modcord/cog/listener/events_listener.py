"""Event listener Cog for Modcord.

This cog has exactly ONE responsibility: handle bot lifecycle events
(on_ready, on_guild_join, on_guild_remove).

Side-effect details (DB writes, file writes) are confined to small,
clearly-named helpers so the event handlers themselves stay readable.
"""

import asyncio
import json

import discord
from discord.ext import commands

from modcord.datatypes.discord_datatypes import GuildID
from modcord.settings.guild_settings_manager import guild_settings_manager
from modcord.util.logger import get_logger

logger = get_logger("events_listener")


class EventsListenerCog(commands.Cog):
    """Handles Discord bot lifecycle events."""

    def __init__(self, bot: discord.Bot) -> None:
        self.bot = bot
        logger.info("[EVENTS LISTENER] Events listener cog loaded")

    # ------------------------------------------------------------------
    # Lifecycle events
    # ------------------------------------------------------------------

    @commands.Cog.listener(name="on_ready")
    async def on_ready(self) -> None:
        """Set bot presence and persist console list to disk."""
        if not self.bot.user:
            logger.warning(
                "[EVENTS LISTENER] Bot partially connected — user info not yet available."
            )
            return

        await self.bot.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="over your server while you're asleep!",
            ),
        )
        logger.info("Bot connected as %s (ID: %s)", self.bot.user, self.bot.user.id)

        # Persist console list for stuff like top.gg and other bot listing sites that want to show our commands. This is a bit hacky but it works and it's not worth caring much just for this.
        await self._write_commands_file()



    @commands.Cog.listener(name="on_guild_join")
    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Initialise and persist default settings for a newly joined guild."""
        guild_id = GuildID(guild.id)
        logger.debug("[EVENTS LISTENER] Bot joined guild: %s (ID: %s)", guild.name, guild.id)

        settings = await guild_settings_manager.get_settings(guild_id)
        await guild_settings_manager.save(guild_id, settings)

        logger.info(
            "[EVENTS LISTENER] Initialized settings for guild '%s' — AI=%s",
            guild.name,
            "enabled" if settings.ai_enabled else "disabled",
        )



    @commands.Cog.listener(name="on_guild_remove")
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        """Delete all guild data when the bot leaves a server."""
        guild_id = GuildID(guild.id)
        logger.debug(
            "[EVENTS LISTENER] Bot removed from guild: %s (ID: %s)", guild.name, guild.id
        )

        # We actually don't delete the data as it's kinda pointless and has no meaning in life.
        return

        success = await guild_settings_manager.delete(guild_id)
        if success:
            logger.info(
                "[EVENTS LISTENER] Cleaned up data for guild '%s' (ID: %s)",
                guild.name,
                guild.id,
            )
        else:
            logger.error(
                "[EVENTS LISTENER] Failed to clean up data for guild '%s' (ID: %s)",
                guild.name,
                guild.id,
            )

    # ------------------------------------------------------------------
    # These methods don't really do anything — they just log the events for now. But it's nice to have them here in case we want to add side effects later.
    # ------------------------------------------------------------------

    async def _write_commands_file(self) -> None:
        """Fetch global commands from Discord and write them to data/commands.json."""
        try:
            commands_data = await self.bot.http.get_global_commands(self.bot.user.id) # type: ignore
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, _write_json, "data/commands.json", commands_data
            )
            logger.debug("[EVENTS LISTENER] commands.json updated.")
        except Exception:
            logger.exception("[EVENTS LISTENER] Failed to write commands.json")


def _write_json(path: str, data: object) -> None:
    """Blocking helper — write *data* as JSON to *path* (run in executor)."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)




def setup(bot: discord.Bot) -> None:
    """Register the EventsListenerCog with the bot."""
    bot.add_cog(EventsListenerCog(bot))