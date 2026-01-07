"""Event listener Cog for Modcord.

This cog handles bot lifecycle events (on_ready) and command error handling.
Message-related events are handled by the MessageListenerCog.
"""

import json
import discord
from discord.ext import commands

from modcord.util.logger import get_logger

logger = get_logger("EVENTS LISTENER")


class EventsListenerCog(commands.Cog):
    """Cog containing bot lifecycle and command error handlers."""

    def __init__(self, bot: discord.Bot):
        """
        Initialize the events listener cog.

        Args:
            bot: The Discord bot instance to attach this cog to.
        """
        self.bot = bot
        logger.info("Events listener cog loaded")

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
            logger.warning("Bot partially connected, but user information not yet available.")

        # Dump all registered commands to a file for reference
        commands = await self.bot.http.get_global_commands(self.bot.user.id) # type: ignore

        with open("data/commands.json", "w") as f:
            f.write(json.dumps(commands, indent=2))


def setup(bot: discord.Bot) -> None:
    """
    Register the EventsListenerCog with the bot.

    Args:
        bot: The Discord bot instance to add this cog to.
    """
    bot.add_cog(EventsListenerCog(bot))