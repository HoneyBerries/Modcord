"""Event listener Cog for Modcord.

This cog handles bot lifecycle events (on_ready) and command error handling.
Message-related events are handled by the MessageListenerCog.
"""

import asyncio
import json
import discord
from discord.ext import commands

from modcord.configuration.guild_settings import guild_settings_manager
from modcord.configuration.app_configuration import app_config
from modcord.ai.ai_moderation_processor import model_state
from modcord.rules_cache.rules_cache_manager import rules_cache_manager
from modcord.util.logger import get_logger
from modcord.moderation import moderation_helper

logger = get_logger("events_listener_cog")



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
        logger.info("Events listener cog loaded")

    @commands.Cog.listener(name='on_ready')
    async def on_ready(self):
        """
        Handle bot startup: initialize presence, rules cache, and batch processing.

        This method:
        1. Updates the bot's Discord presence based on AI model state
        2. Starts the periodic rules cache refresh task
        3. Registers the batch processing callback
        4. Puts all registered commands into a file called commands.json for reference
        """
        if self.bot.user:
            await self._update_presence()
            logger.info(f"Bot connected as {self.bot.user} (ID: {self.bot.user.id})")
        else:
            logger.warning("Bot partially connected, but user information not yet available.")

        logger.info("--==--==--==--==--==--==--==--==--==--==--==--==--==--==--==--==--")

        # Start the rules and guidelines cache refresh task
        logger.info("Starting server rules and channel guidelines cache refresh task...")
        interval_seconds = float(app_config.get("rules_cache_refresh", {}).get("interval_seconds", 600.0))
        asyncio.create_task(rules_cache_manager.start_periodic_task(self.bot, interval_seconds))

        # Set up batch processing callback for global batching
        logger.info("Setting up batch processing callback...")
        guild_settings_manager.set_batch_processing_callback(
            lambda batches: moderation_helper.process_message_batches(self, batches)
        )

        commands = await self.bot.http.get_global_commands(self.bot.user.id)
        with open("config/commands.json", "w") as f:
            f.write(json.dumps(commands, indent=4))

    async def _update_presence(self) -> None:
        """
        Update bot's Discord presence based on AI model availability.

        If the AI model is available, sets the bot status to online and a friendly message.
        If not, sets the status to idle and a less enthusiastic message.
        """
        if not self.bot.user:
            return

        if model_state.available:
            status = discord.Status.online
            activity_name = "over your server while you're asleep!"
        else:
            status = discord.Status.idle
            activity_name = "your server drunkenly because the AI is tired."

        await self.bot.change_presence(
            status=status,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=activity_name,
            )
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