"""
Core bot class and setup.
"""

import discord
from discord.ext import commands

from ..config.logger import get_logger

logger = get_logger(__name__)

class Bot(commands.Bot):
    """
    The main bot class.
    """
    def __init__(self):
        super().__init__(intents=discord.Intents.all())
        self.load_cogs()

    def load_cogs(self):
        """
        Loads all cogs from the cogs directory.
        """
        cog_files = [
            'bot.cogs.general',
            'bot.cogs.moderation',
            'bot.cogs.debug',
            'bot.cogs.events'
        ]

        for cog in cog_files:
            try:
                self.load_extension(cog)
                logger.info(f"Loaded cog: {cog}")
            except Exception as e:
                logger.error(f"Failed to load cog {cog}: {e}")

    async def on_ready(self):
        """
        Called when the bot is ready.
        """
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        logger.info('------')
