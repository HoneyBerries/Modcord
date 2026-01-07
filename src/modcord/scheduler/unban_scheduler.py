"""
Simple scheduled unban manager using discord.ext.tasks.
Processes expired bans from a persistent store on a periodic interval.
"""

from __future__ import annotations

import datetime
import discord
from discord.ext import tasks, commands

from modcord.datatypes.discord_datatypes import UserID, GuildID
from modcord.util.logger import get_logger

# In a real app, you would import your actual database manager here
# from modcord.settings.guild_settings_manager import guild_settings_manager

logger = get_logger("unban_scheduler")

class UnbanScheduler(commands.Cog):
    """
    Manages delayed unban operations by checking for expired bans 
    on a regular interval.
    """

    def __init__(self, bot: discord.Bot):
        self.bot = bot
        # Start the background checker
        self.check_unbans.start()

    def cog_unload(self):
        """Cleanly stop the task when the cog is removed."""
        self.check_unbans.cancel()

    @tasks.loop(seconds=60.0)
    async def check_unbans(self):
        """
        Periodic task that checks for users whose ban duration has expired.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        logger.debug("Checking for expired bans at %s", now)

        # --- DATABASE LOGIC PLACEHOLDER ---
        # In a real implementation, you would query your DB for:
        # SELECT * FROM temp_bans WHERE unban_at <= now
        expired_bans = [] # This would be a list of ban objects from your DB
        # ----------------------------------

        for ban in expired_bans:
            await self.execute_unban(ban.guild_id, ban.user_id, ban.reason)

    async def execute_unban(self, guild_id: int, user_id: int, reason: str):
        """
        Attempts to unban a user from a specific guild.
        """
        guild = self.bot.get_guild(guild_id)
        if not guild:
            logger.warning("Could not find guild %s to perform unban.", guild_id)
            return

        try:
            # We use discord.Object to unban via ID without needing to fetch the whole user
            user_obj = discord.Object(id=user_id)
            await guild.unban(user_obj, reason=f"[Auto-Unban] {reason}")
            
            # --- DATABASE LOGIC PLACEHOLDER ---
            # Remove the ban record from your DB so we don't try again
            # await database.remove_temp_ban(guild_id, user_id)
            # ----------------------------------
            
            logger.info("Successfully auto-unbanned %s in guild %s", user_id, guild.name)

        except discord.NotFound:
            logger.info("User %s was already unbanned from %s.", user_id, guild.name)
            # Still remove from DB since it's no longer needed
        except discord.Forbidden:
            logger.error("Missing permissions to unban %s in %s.", user_id, guild.name)
        except Exception as e:
            logger.error("Unexpected error unbanning %s: %s", user_id, e)

    @check_unbans.before_loop
    async def before_unban_check(self):
        """Ensure the bot is ready before querying guilds."""
        await self.bot.wait_until_ready()

    # Example of how you would "Schedule" a new unban now
    async def schedule_unban(self, guild_id: int, user_id: int, duration_seconds: float, reason: str):
        """
        Instead of a heap, we just calculate the timestamp and save it to the DB.
        """
        unban_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=duration_seconds)
        
        # --- DATABASE LOGIC PLACEHOLDER ---
        # await database.save_temp_ban(guild_id, user_id, unban_at, reason)
        # ----------------------------------
        
        logger.info("Scheduled unban for %s in %s for %s", user_id, guild_id, unban_at)

def setup(bot: discord.Bot):
    """Entry point for bot.load_extension."""
    bot.add_cog(UnbanScheduler(bot))