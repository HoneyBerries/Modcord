"""
Event handlers cog for the Discord Moderation Bot.
"""

import asyncio
import discord
from discord.ext import commands

from ..config.logger import get_logger
from ..models.action import ActionType
from ..services.ai_service import get_ai_service
from ..services.moderation_service import ModerationService
from ..bot_state import bot_state

logger = get_logger(__name__)

class EventsCog(commands.Cog):
    """
    Cog containing all bot event handlers.
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.moderation_service = ModerationService(bot)
        self.ai_service = get_ai_service()
        logger.info("Events cog loaded")

    @commands.Cog.listener()
    async def on_ready(self):
        """
        Fired when the bot successfully connects to Discord.
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
        
        logger.info("Starting background tasks...")
        asyncio.create_task(self._refresh_rules_cache_task())
        self.ai_service.start()
        logger.info("=" * 60)

    async def _refresh_rules_cache_task(self):
        """
        Background task to refresh server rules cache.
        """
        while True:
            try:
                logger.info("Refreshing server rules cache...")
                for guild in self.bot.guilds:
                    try:
                        rules_text = await self.moderation_service.fetch_server_rules_from_channel(guild)
                        bot_state.set_server_rules(guild.id, rules_text)
                        if rules_text:
                            logger.info(f"Cached rules for {guild.name} ({len(rules_text)} characters)")
                        else:
                            logger.warning(f"No rules found for {guild.name}")
                    except Exception as e:
                        logger.error(f"Failed to fetch rules for {guild.name}: {e}")
                        if guild.id not in bot_state.server_rules_cache:
                            bot_state.set_server_rules(guild.id, "")
                logger.info(f"Rules cache refreshed for {len(bot_state.server_rules_cache)} guilds")
            except Exception as e:
                logger.error(f"Error during rules cache refresh: {e}")
            await asyncio.sleep(300)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Processes incoming messages for AI-powered moderation.
        """
        if message.author.bot or (
            isinstance(message.author, discord.Member) and 
            message.author.guild_permissions.administrator
        ):
            return

        actual_content = message.clean_content
        if not actual_content:
            return

        message_data = {
            "role": "user", 
            "content": actual_content, 
            "username": str(message.author)
        }
        bot_state.add_message_to_history(message.channel.id, message_data)

        server_rules = bot_state.get_server_rules(message.guild.id) if message.guild else ""

        try:
            action, reason = await self.ai_service.get_appropriate_action(
                current_message=actual_content,
                history=bot_state.get_chat_history(message.channel.id),
                username=message.author.name,
                server_rules=server_rules
            )

            if action != ActionType.NULL:
                await self.moderation_service.take_action(action, reason, message)
                
        except Exception as e:
            logger.error(f"Error in AI moderation for message from {message.author}: {e}")

    @commands.Cog.listener()
    async def on_application_command_error(self, ctx: discord.ApplicationContext, error: discord.DiscordException):
        """
        Global error handler for all application commands.
        """
        if isinstance(error, commands.CommandNotFound):
            return

        logger.error(f"Error in command '{ctx.command.name}': {error}", exc_info=True)

        try:
            await ctx.respond("An unexpected error occurred while running this command.", ephemeral=True)
        except discord.InteractionResponded:
            await ctx.followup.send("An unexpected error occurred while running this command.", ephemeral=True)

def setup(bot):
    bot.add_cog(EventsCog(bot))