"""
Event handlers cog for the Discord Moderation Bot.
"""

import asyncio

import discord
from discord.ext import commands

from logger import get_logger
from actions import ActionType
import bot_helper
from bot_config import bot_config

logger = get_logger("events_cog")


class EventsCog(commands.Cog):
    """
    Cog containing all bot event handlers.
    """
    
    def __init__(self, bot):
        self.bot = bot
        logger.info("Events cog loaded")

    @commands.Cog.listener()
    async def on_ready(self):
        """
        Fired when the bot successfully connects to Discord.
        Sets presence, starts background tasks, and logs connection.
        """
        if self.bot.user:
            await self.bot.change_presence(
                status=discord.Status.online,
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name="for rule violations"
                )
            )
            logger.info(f"Bot connected as {self.bot.user} (ID: {self.bot.user.id})")
        else:
            logger.warning("Bot connected, but user information not yet available.")
        
        # Start the rules cache refresh task
        logger.info("Starting server rules cache refresh task...")
        asyncio.create_task(self._refresh_rules_cache_task())
        
        # Start AI batch processing worker
        logger.info("Starting AI batch processing worker...")
        try:
            import ai_model as ai
            ai.start_batch_worker()
            logger.info("[AI] Batch processing worker started.")
        except Exception as e:
            logger.error(f"Failed to start AI batch processing worker: {e}")
        logger.info("=" * 60)

    async def _refresh_rules_cache_task(self):
        """
        Background task to refresh server rules cache.
        """
        try:
            await bot_helper.refresh_rules_cache(self.bot, bot_config.server_rules_cache)
        except Exception as e:
            logger.error(f"Error in rules cache refresh task: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Processes incoming messages for AI-powered moderation.
        """
        # Ignore messages from bots and administrators
        logger.debug(f"Received message from {message.author}: {message.clean_content}")
        if message.author.bot or (
            isinstance(message.author, discord.Member) and 
            message.author.guild_permissions.administrator
        ):
            return

        # Skip empty messages or messages with only whitespace
        actual_content = message.clean_content
        if not actual_content:
            return

        # Store message in the channel's history for contextual analysis
        message_data = {
            "role": "user", 
            "content": actual_content, 
            "username": str(message.author)
        }
        bot_config.add_message_to_history(message.channel.id, message_data)

        # Get server rules
        server_rules = bot_config.get_server_rules(message.guild.id) if message.guild else ""

        # Get a moderation action from the AI model
        try:
            import ai_model as ai
            action, reason = await ai.get_appropriate_action(
                current_message=actual_content,
                history=bot_config.get_chat_history(message.channel.id),
                username=message.author.name,
                server_rules=server_rules
            )

            if action != ActionType.NULL:
                await bot_helper.take_action(action, reason, message, self.bot.user)
                
        except Exception as e:
            logger.error(f"Error in AI moderation for message from {message.author}: {e}")


    @commands.Cog.listener()
    async def on_application_command_error(self, ctx: discord.ApplicationContext, error: discord.DiscordException):
        """
        Global error handler for all application commands.
        Logs the error and sends a generic error message to the user.
        """
        # Ignore commands that don't exist
        if isinstance(error, commands.CommandNotFound):
            return

        # Log the error with traceback
        logger.error(f"Error in command '{ctx.command.name}': {error}", exc_info=True)

        # Respond to the user with a generic error message
        # Use a try-except block in case the interaction has already been responded to
        try:
            await ctx.respond("An unexpected error occurred while running this command.", ephemeral=True)
        except discord.InteractionResponded:
            await ctx.followup.send("An unexpected error occurred while running this command.", ephemeral=True)


def setup(bot):
    """Setup function for the cog."""
    bot.add_cog(EventsCog(bot))