"""Guild Join and Leave listener Cog

This Cog handles events when the bot joins or leaves a guild (server). It ensures that when the bot joins a guild, default settings are created and persisted.
"""

import discord
from discord.ext import commands

from modcord.settings.guild_settings_manager import guild_settings_manager
from modcord.datatypes.discord_datatypes import GuildID
from modcord.util.logger import get_logger

logger = get_logger("GUILD LISTENER")


class GuildListener(commands.Cog):
    """Listener Cog for handling guild join and leave events."""

    def __init__(self, bot: discord.Bot):
        """Store the Discord bot reference."""
        self.bot = bot
        logger.info("Guild listener cog loaded")


    @commands.Cog.listener(name='on_guild_join')
    async def on_guild_join(self, guild: discord.Guild):
        """
        Handle bot joining a new server.

        This method:
        1. Creates default guild settings with all features enabled
        2. Persists the settings to the database
        3. Logs the successful setup
        """
        guild_id = GuildID(guild.id)
        logger.debug(f"Bot joined guild: {guild.name} (ID: {guild.id})")
        
        # Get or create settings (this will use the new defaults with everything enabled)
        settings = await guild_settings_manager.get_settings(guild_id)
        
        # Explicitly save to ensure it's persisted to the database
        await guild_settings_manager.save(guild_id, settings)
        
        logger.debug(
            f"Initialized settings for {guild.name}: "
            f"AI={'enabled' if settings.ai_enabled else 'disabled'}, "
            f"Actions={'all enabled' if all([settings.auto_warn_enabled, settings.auto_delete_enabled, settings.auto_timeout_enabled, settings.auto_kick_enabled, settings.auto_ban_enabled, settings.auto_review_enabled]) else 'some disabled'}"
        )


    @commands.Cog.listener(name='on_guild_remove')
    async def on_guild_remove(self, guild: discord.Guild):
        """
        Handle bot leaving or being removed from a server.

        This method:
        1. Deletes all guild-related data from the database
        2. Removes the guild from the in-memory cache
        3. Cleans up moderation history
        4. Logs the removal
        
        This is good practice for data hygiene and privacy - when the bot
        is no longer in a server, there's no reason to keep their data.
        """
        guild_id = GuildID(guild.id)
        logger.debug(f"Bot removed from guild: {guild.name} (ID: {guild.id})")
        
        # Delete all data for this guild
        success = await guild_settings_manager.delete(guild_id)
        
        if success:
            logger.debug(
                f"[EVENTS LISTENER] Successfully cleaned up all data for guild: {guild.name} (ID: {guild.id})"
            )
        else:
            logger.error(
                f"[EVENTS LISTENER] Failed to clean up data for guild: {guild.name} (ID: {guild.id})"
            )

def setup(bot: discord.Bot) -> None:
    """
    Register the GuildListenerCog with the bot.
    
    Args:
        bot: The Discord bot instance to attach this cog to.
    """
    bot.add_cog(GuildListener(bot))