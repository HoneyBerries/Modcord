"""Event listener Cog for Modcord.

This cog handles bot lifecycle events (on_ready) and command error handling.
Message-related events are handled by the MessageListenerCog.
"""

import asyncio
import discord
from discord.ext import commands

from modcord.configuration.guild_settings import guild_settings_manager
from modcord.ai.ai_moderation_processor import model_state
from modcord.util.logger import get_logger
from modcord.util import moderation_helper

logger = get_logger("events_listener_cog")


class EventsListenerCog(commands.Cog):
    """Cog containing bot lifecycle and command error handlers."""

    def __init__(self, discord_bot_instance):
        """Initialize the events listener cog.
        
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
        """Handle bot startup: initialize presence, rules cache, and batch processing.
        
        This method:
        1. Updates the bot's Discord presence based on AI model state
        2. Starts the periodic rules cache refresh task
        3. Registers the batch processing callback
        """
        if self.bot.user:
            await self._update_presence()
            logger.info(f"Bot connected as {self.bot.user} (ID: {self.bot.user.id})")
        else:
            logger.warning("Bot partially connected, but user information not yet available.")
        
        logger.info("--==--==--==--==--==--==--==--==--==--==--==--==--==--==--==--==--")
        
        # Start the rules cache refresh task
        logger.info("Starting server rules cache refresh task...")
        asyncio.create_task(moderation_helper.refresh_rules_cache_task(self))
						
        # Set up batch processing callback for channel-based batching
        logger.info("Setting up batch processing callback...")
        guild_settings_manager.set_batch_processing_callback(
            lambda batch: moderation_helper.process_message_batch(self, batch)
        )
        

    async def _update_presence(self) -> None:
        """Update bot's Discord presence based on AI model availability."""
        if not self.bot.user:
            return

        if model_state.available:
            status = discord.Status.online
            activity_name = "over your server while you're asleep!"
        else:
            status = discord.Status.idle
            activity_name = f"your server drunkenly because the AI is tired."

        await self.bot.change_presence(
            status=status,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=activity_name,
            )
        )


    @commands.Cog.listener(name='on_application_command_error')
    async def on_application_command_error(self, application_context: discord.ApplicationContext, error: Exception):
        """Handle errors from application commands with logging and user feedback.
        
        Parameters
        ----------
        application_context:
            The command invocation context.
        error:
            The exception raised during command execution.
        """
        # Ignore commands that don't exist
        if isinstance(error, commands.CommandNotFound):
            return

        # Log the error with full traceback
        command_name = getattr(application_context.command, 'name', '<unknown>')
        logger.error(f"Error in command '{command_name}': {error}", exc_info=True)

        # Send a user-friendly error message
        error_message = "A :bug: showed up while running this command."
        try:
            await application_context.respond(error_message, ephemeral=True)
        except discord.InteractionResponded:
            await application_context.followup.send(error_message, ephemeral=True)




def setup(discord_bot_instance):
    """Register the EventsListenerCog with the bot.
    
    Parameters
    ----------
    discord_bot_instance:
        The Discord bot instance to add this cog to.
    """
    discord_bot_instance.add_cog(EventsListenerCog(discord_bot_instance))
