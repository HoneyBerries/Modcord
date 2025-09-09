"""
General commands cog for the Discord Moderation Bot.
"""

import discord
from discord.ext import commands

from ..logger import get_logger

logger = get_logger("general_cog")


class GeneralCog(commands.Cog):
    """
    Cog containing general utility commands.
    """
    
    def __init__(self, bot):
        self.bot = bot
        logger.info("General cog loaded")

    @commands.slash_command(name="test", description="Checks if the bot is online and its latency.")
    async def test(self, ctx: discord.ApplicationContext):
        """
        A simple health-check command to verify bot status and latency.
        """
        latency_ms = self.bot.latency * 1000
        await ctx.respond(
            f":white_check_mark: I am online and working!\n**Latency**: {latency_ms:.2f} ms.", 
            ephemeral=True
        )


def setup(bot):
    """Setup function for the cog."""
    bot.add_cog(GeneralCog(bot))