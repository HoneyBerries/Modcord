"""Cog for periodic synchronization of channel guidelines across all guilds."""

from __future__ import annotations

import discord
from discord.ext import tasks, commands

from modcord.configuration.app_configuration import app_config
from modcord.settings.guild_settings_manager import guild_settings_manager
from modcord.datatypes.discord_datatypes import GuildID, ChannelID
from modcord.util.discord import collector
from modcord.util.logger import get_logger

logger = get_logger("guidelines_sync")

class GuidelinesSyncCog(commands.Cog):
    """
    A Cog that handles the periodic collection and persistence of channel-specific guidelines.
    """
    def __init__(self, bot: discord.Bot):
        self.bot = bot
        # Dynamically set the interval from your app_config
        self.sync_loop.change_interval(seconds=app_config.guidelines_sync_interval)
        # Start the background task
        self.sync_loop.start()

    def cog_unload(self):
        """Stops the background task when the cog is unloaded."""
        self.sync_loop.cancel()

    async def sync_guild_guidelines(self, guild: discord.Guild) -> None:
        """Sync guidelines for all text channels in a guild."""
        guild_id = GuildID(guild.id)
        settings = await guild_settings_manager.get_settings(guild_id)
        
        for ch in guild.text_channels:
            # Collects the topic or specific text from the channel
            text = collector.collect_channel_topic(ch)
            settings.channel_guidelines[ChannelID(ch.id)] = text
            
        await guild_settings_manager.save(guild_id, settings)

    @tasks.loop()
    async def sync_loop(self):
        """The main loop that iterates over all guilds to sync channel guidelines."""
        logger.info("Starting periodic guidelines sync for %d guilds", len(self.bot.guilds))
        
        for guild in self.bot.guilds:
            try:
                await self.sync_guild_guidelines(guild)
            except Exception as exc:
                # Ensures one guild error doesn't stop the entire background process
                logger.error("[%s] Failed to sync guidelines: %s", guild.name, exc)

    @sync_loop.before_loop
    async def before_sync_loop(self):
        """Wait for the bot to be fully connected before starting the loop."""
        await self.bot.wait_until_ready()

def setup(bot: discord.Bot):
    """Entry point for bot.load_extension."""
    bot.add_cog(GuidelinesSyncCog(bot))