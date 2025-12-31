"""Event listener Cog for Modcord.

This cog handles bot lifecycle events (on_ready) and command error handling.
Message-related events are handled by the MessageListenerCog.
"""

import json
import discord
from discord.ext import commands

from modcord.util.logger import get_logger
from modcord.settings.guild_settings_manager import guild_settings_manager
from modcord.datatypes.discord_datatypes import GuildID

logger = get_logger("events_listener")


class EventsListenerCog(commands.Cog):
    """Cog containing bot lifecycle and command error handlers."""

    def __init__(self, discord_bot_instance):
        """
        Initialize the events listener cog.

        Parameters
        ----------
        discord_bot_instance:
            The Discord bot instance to attach this cog to.
        """
        self.bot = discord_bot_instance
        self.discord_bot_instance = discord_bot_instance
        logger.info("[EVENTS LISTENER] Events listener cog loaded")

    @commands.Cog.listener(name='on_ready')
    async def on_ready(self):
        """
        Handle bot startup: initialize presence.

        This method:
        1. Updates the bot's Discord presence based on AI model state
        2. Puts all registered commands into a file called commands.json for reference
        """
        if self.bot.user:

            # Set initial presence
            await self.bot.change_presence(
                status=discord.Status.online,
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name="over your server while you're asleep!"
                )
            )

            logger.info(f"Bot connected as {self.bot.user} (ID: {self.bot.user.id})")
        else:
            logger.warning("[EVENTS LISTENER] Bot partially connected, but user information not yet available.")

        commands = await self.bot.http.get_global_commands(self.bot.user.id)

        with open("data/commands.json", "w") as f:
            f.write(json.dumps(commands, indent=2))
        

    @commands.Cog.listener(name='on_guild_join')
    async def on_guild_join(self, guild: discord.Guild):
        """
        Handle bot joining a new server.

        This method:
        1. Creates default guild settings with all features enabled
        2. Persists the settings to the database
        3. Logs the successful setup
        """
        guild_id = GuildID(guild.id)
        logger.debug(f"[EVENTS LISTENER] Bot joined guild: {guild.name} (ID: {guild.id})")
        
        # Get or create settings (this will use the new defaults with everything enabled)
        settings = guild_settings_manager.get(guild_id)
        
        # Explicitly save to ensure it's persisted to the database
        guild_settings_manager.save(guild_id)
        
        logger.debug(
            f"[EVENTS LISTENER] Initialized settings for {guild.name}: "
            f"AI={'enabled' if settings.ai_enabled else 'disabled'}, "
            f"Actions={'all enabled' if all([settings.auto_warn_enabled, settings.auto_delete_enabled, settings.auto_timeout_enabled, settings.auto_kick_enabled, settings.auto_ban_enabled, settings.auto_review_enabled]) else 'some disabled'}"
        )


    @commands.Cog.listener(name='on_guild_remove')
    async def on_guild_remove(self, guild: discord.Guild):
        """
        Handle bot leaving or being removed from a server.

        This method:
        1. Deletes all guild-related data from the database
        2. Removes the guild from the in-memory cache
        3. Cleans up moderation history
        4. Logs the removal
        
        This is good practice for data hygiene and privacy - when the bot
        is no longer in a server, there's no reason to keep their data.
        """
        guild_id = GuildID(guild.id)
        logger.debug(f"[EVENTS LISTENER] Bot removed from guild: {guild.name} (ID: {guild.id})")
        
        # Delete all data for this guild
        success = await guild_settings_manager.delete(guild_id)
        
        if success:
            logger.debug(
                f"[EVENTS LISTENER] Successfully cleaned up all data for guild: {guild.name} (ID: {guild.id})"
            )
        else:
            logger.error(
                f"[EVENTS LISTENER] Failed to clean up data for guild: {guild.name} (ID: {guild.id})"
            )


def setup(discord_bot_instance):
    """
    Register the EventsListenerCog with the bot.

    Parameters
    ----------
    discord_bot_instance:
        The Discord bot instance to add this cog to.
    """
    discord_bot_instance.add_cog(EventsListenerCog(discord_bot_instance))