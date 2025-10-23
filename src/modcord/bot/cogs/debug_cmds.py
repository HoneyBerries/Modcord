"""
Debug commands cog for the Discord Moderation Bot.
"""

import datetime

import discord
from discord.ext import commands

from modcord.configuration.guild_settings import guild_settings_manager
from modcord.util.logger import get_logger

logger = get_logger("debug_commands")

class DebugCog(commands.Cog):
    """Cog for debug commands."""

    debug = discord.SlashCommandGroup("debug", "Debug commands for bot administration")

    def __init__(self, bot: discord.Bot):
        self.bot = bot

    @debug.command(name="test", description="Test command to verify the bot is responsive")
    async def test(self, application_context: discord.ApplicationContext) -> None:
        """Test command to verify the bot is responsive."""
        try:
            await application_context.defer(ephemeral=True)
            embed = discord.Embed(
                title="✅ Bot Test Successful",
                description="The bot is responsive and working correctly.",
                color=discord.Color.green(),
            )
            embed.add_field(name="Guild", value=application_context.guild.name, inline=False)
            embed.add_field(name="User", value=application_context.user.mention, inline=False)
            await application_context.send_followup(embed=embed)
            logger.debug(f"Test command executed by {application_context.user} in {application_context.guild.name}")
        except Exception as e:
            logger.error(f"Error in test command: {e}")
            await application_context.send_followup(content=f"❌ Error: {e}", ephemeral=True)

    @debug.command(name="purge", description="Delete all messages in the current channel")
    async def purge(self, application_context: discord.ApplicationContext) -> None:
        """Delete all messages in the current channel."""
        try:
            await application_context.defer(ephemeral=True)
            guild = application_context.guild
            channel = application_context.channel

            if not guild or not channel:
                await application_context.send_followup(content="❌ This command must be used in a guild channel.", ephemeral=True)
                return

            deleted = await channel.purge(limit=None)
            embed = discord.Embed(
                title="✅ Channel Purged",
                description=f"Deleted {len(deleted)} messages from {channel.mention}",
                color=discord.Color.green(),
            )
            await application_context.send_followup(embed=embed)
            logger.debug(f"Purged {len(deleted)} messages from {channel.name} in {guild.name}")
        except Exception as e:
            logger.error(f"Error in purge command: {e}")
            await application_context.send_followup(content=f"❌ Error: {e}", ephemeral=True)

    @debug.command(name="refresh_rules", description="Manually refresh the server rules cache")
    async def refresh_rules(self, application_context: discord.ApplicationContext) -> None:
        """Manually refresh the server rules cache from the database."""
        try:
            await application_context.defer(ephemeral=True)
            guild = application_context.guild

            if not guild:
                await application_context.send_followup(content="❌ This command must be used in a guild.", ephemeral=True)
                return

            settings = guild_settings_manager.get_guild_settings(guild.id)
            embed = discord.Embed(
                title="✅ Rules Cache Refreshed",
                description=f"Rules for {guild.name} have been refreshed from the database.",
                color=discord.Color.green(),
            )
            embed.add_field(name="Rules Length", value=str(len(settings.rules)), inline=False)
            await application_context.send_followup(embed=embed)
            logger.debug(f"Rules cache refreshed for guild {guild.name}")
        except Exception as e:
            logger.error(f"Error in refresh_rules command: {e}")
            await application_context.send_followup(content=f"❌ Error: {e}", ephemeral=True)

    @debug.command(name="show_rules", description="Display the current server rules")
    async def show_rules(self, application_context: discord.ApplicationContext) -> None:
        """Display the current server rules cached in memory."""
        try:
            await application_context.defer(ephemeral=True)
            guild = application_context.guild

            if not guild:
                await application_context.send_followup(content="❌ This command must be used in a guild.", ephemeral=True)
                return

            rules = guild_settings_manager.get_server_rules(guild.id)
            if not rules:
                embed = discord.Embed(
                    title="📋 Server Rules",
                    description="No rules have been set for this server.",
                    color=discord.Color.orange(),
                )
            else:
                embed = discord.Embed(
                    title="📋 Server Rules",
                    description=rules,
                    color=discord.Color.blue(),
                )
            await application_context.send_followup(embed=embed, ephemeral=True)
            logger.debug(f"Displayed rules for guild {guild.name}")
        except Exception as e:
            logger.error(f"Error in show_rules command: {e}")
            await application_context.send_followup(content=f"❌ Error: {e}", ephemeral=True)


def setup(bot: discord.Bot) -> None:
    """Register the debug cog and command group with the bot."""
    bot.add_cog(DebugCog(bot))