"""
Simple scheduled unban manager using discord.ext.tasks.
Processes expired bans from a persistent store on a periodic interval.
"""

from __future__ import annotations

import datetime
import discord
from discord.ext import tasks, commands

from modcord.util.logger import get_logger
from modcord.database import database as db

logger = get_logger("UNBAN SCHEDULER")

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

    @tasks.loop(seconds=2.0)
    async def check_unbans(self):
        """
        Periodic task that checks for users whose ban duration has expired.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        current_timestamp = int(now.timestamp())
        logger.debug("Checking for expired bans at %s", now)

        # Query database for expired bans
        async with db.database.get_connection() as conn:
            expired_bans = await db.database.moderation_action_storage.get_expired_bans(conn, current_timestamp)

        for ban in expired_bans:
            await self.execute_unban(ban["guild_id"], ban["user_id"], ban["reason"])


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
            
            # Delete the ban record from DB
            async with db.database.get_connection() as conn:
                await db.database.moderation_action_storage.delete_ban(conn, guild_id, user_id)
            
            logger.debug("Successfully auto-unbanned %s in guild %s", user_id, guild.name)

        except discord.NotFound:
            logger.warning("User %s was already unbanned from %s.", user_id, guild.name)
            # Delete from DB since it's no longer needed
            async with db.database.get_connection() as conn:
                await db.database.moderation_action_storage.delete_ban(conn, guild_id, user_id)
        except discord.Forbidden:
            logger.error("Missing permissions to unban %s in %s. Will retry later.", user_id, guild.name)
            # Keep ban record in DB for retry - don't remove it
        except Exception as e:
            logger.error("Unexpected error unbanning %s: %s. Will retry later.", user_id, e)
            # Keep ban record in DB for retry - don't remove it

    @check_unbans.before_loop
    async def before_unban_check(self):
        """Ensure the bot is ready before querying guilds."""
        await self.bot.wait_until_ready()

    # Example of how you would "Schedule" a new unban now
    async def schedule_unban(self, guild_id: int, user_id: int, duration_seconds: float, reason: str = "Ban duration expired"):
        """
        Instead of a heap, we just calculate the timestamp and save it to the DB.
        
        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID
            duration_seconds: How long until the unban (in seconds)
            reason: Reason for the ban (default: "Ban duration expired")
        """
        unban_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=duration_seconds)
        unban_timestamp = int(unban_at.timestamp())
        
        # Save to database (will update if ban already exists)
        async with db.database.get_connection() as conn:
            await db.database.moderation_action_storage.save_temp_ban(conn, guild_id, user_id, unban_timestamp, reason)
        
        logger.info("Scheduled unban for %s in guild %s at %s (timestamp: %s)", user_id, guild_id, unban_at, unban_timestamp)


def setup(bot: discord.Bot):
    """Entry point for bot.load_extension."""
    bot.add_cog(UnbanScheduler(bot))