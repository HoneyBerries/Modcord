"""Event listener Cog for Modcord.

This cog handles bot lifecycle events (on_ready) and command error handling.
Message-related events are handled by the MessageListenerCog.
"""

import json
import discord
from discord.ext import commands

from modcord.util.logger import get_logger

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
            await self._update_presence()
            logger.info(f"Bot connected as {self.bot.user} (ID: {self.bot.user.id})")
        else:
            logger.warning("[EVENTS LISTENER] Bot partially connected, but user information not yet available.")

        commands = await self.bot.http.get_global_commands(self.bot.user.id)

        with open("data/commands.json", "w") as f:
            f.write(json.dumps(commands, indent=2))

    async def _update_presence(self) -> None:
        """
        Update bot's Discord presence.

        Sets the bot status to online with a friendly watching message.
        AI availability is handled per-request, not via global state.
        """
        if not self.bot.user:
            return

        await self.bot.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="over your server while you're asleep!",
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
