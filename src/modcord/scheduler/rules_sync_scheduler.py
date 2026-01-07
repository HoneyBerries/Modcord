"""Cog for periodic synchronization of server rules across all guilds."""

from __future__ import annotations

import discord
from discord.ext import tasks, commands

from modcord.configuration.app_configuration import app_config
from modcord.settings.guild_settings_manager import guild_settings_manager
from modcord.datatypes.discord_datatypes import GuildID
from modcord.util.discord import collector
from modcord.util.logger import get_logger

logger = get_logger("RULES SYNC SCHEDULER")

class RulesSyncScheduler(commands.Cog):
    """
    A Cog that handles the periodic collection and persistence of server rules.
    """
    def __init__(self, bot: discord.Bot):
        self.bot = bot
        # Dynamically set the interval from your app_config
        self.sync_loop.change_interval(seconds=app_config.rules_sync_interval)
        # Start the background task
        self.sync_loop.start()

    def cog_unload(self):
        """Stops the background task when the cog is unloaded."""
        self.sync_loop.cancel()

    async def sync_rules(self, guild: discord.Guild) -> str:
        """Collect rules from rule-like channels and persist to guild settings."""
        rules_text = await collector.collect_rules(guild)
        await guild_settings_manager.update(GuildID(guild.id), rules=rules_text)
        return rules_text

    @tasks.loop()
    async def sync_loop(self):
        """The main loop that iterates over all guilds the bot is in."""
        logger.info("Starting periodic rules sync for %d guilds", len(self.bot.guilds))
        
        for guild in self.bot.guilds:
            try:
                await self.sync_rules(guild)
            except Exception as exc:
                # We catch errors here so one failing guild doesn't stop the whole loop
                logger.error("Failed to sync rules for %s: %s", guild.name, exc)

    @sync_loop.before_loop
    async def before_sync_loop(self):
        """Wait for the bot to be fully connected before starting the loop."""
        await self.bot.wait_until_ready()

def setup(bot: discord.Bot):
    """Entry point for bot.load_extension."""
    bot.add_cog(RulesSyncScheduler(bot))