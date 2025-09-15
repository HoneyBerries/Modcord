"""
General commands cog for the Discord Moderation Bot.
"""

import discord
from discord.ext import commands

from modcord.logger import get_logger

logger = get_logger("general_cog")


class GeneralCog(commands.Cog):
    """
    Cog containing general utility and test commands.
    """

    def __init__(self, discord_bot_instance):
        self.discord_bot_instance = discord_bot_instance
        logger.info("General cog loaded")

    @commands.slash_command(
        name="test",
        description="Checks if the bot is online and its latency."
    )
    async def test(self, application_context: discord.ApplicationContext):
        """
        A simple health-check command to verify bot status and latency.
        """
        latency_milliseconds = self.discord_bot_instance.latency * 1000
        await application_context.respond(
            f":white_check_mark: I am online and working!\n"
            f"**Latency**: {latency_milliseconds:.2f} ms.",
            ephemeral=True
        )


def setup(discord_bot_instance):
    """Setup function for the cog."""
    discord_bot_instance.add_cog(GeneralCog(discord_bot_instance))
