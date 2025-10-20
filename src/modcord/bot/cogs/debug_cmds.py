"""
Debug commands cog for the Discord Moderation Bot.
"""

import datetime

import discord
from discord.ext import commands

from modcord.configuration.guild_settings import guild_settings_manager
from modcord.bot import rules_manager
from modcord.util.logger import get_logger

logger = get_logger("debug_cog")


class DebugCog(commands.Cog):
    """
    Cog containing debugging and administrative commands.
    """

    def __init__(self, discord_bot_instance):
        """Store the Discord bot reference and log cog initialization."""
        self.discord_bot_instance = discord_bot_instance
        logger.info("Debug cog loaded")

    @commands.slash_command(
        name="test",
        description="Checks if the bot is online and its round trip time."
    )
    async def test(self, application_context: discord.ApplicationContext):
        """
        A simple health-check command to verify bot status and round trip time.

        Parameters
        ----------
        application_context:
            Slash command invocation context supplied by Py-Cord.
        """
        latency_milliseconds = self.discord_bot_instance.latency * 1000
        await application_context.respond(
            f":white_check_mark: I am online and working!\n"
            f"**Round Trip Time**: {latency_milliseconds:.2f} ms.",
            ephemeral=True
        )

    @commands.slash_command(
        name="purge",
        description="Delete ALL messages from the bot in the current channel.")
    async def purge(self, application_context: discord.ApplicationContext):
        """
        Delete all messages sent by everyone in the current channel.
        """
        channel = application_context.channel
        if not channel:
            await application_context.respond("No channel found.", ephemeral=True)
            return
        
        # Make sure that the user has administrator permissions
        member = application_context.author
        if not isinstance(member, discord.Member) or not member.guild_permissions.administrator:
            await application_context.respond("You do not have permission to use this command.", ephemeral=True)
            return

        try:
            await application_context.defer()
            await channel.purge()
            await application_context.send_followup("All messages deleted.", ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to purge messages in {channel.name}: {e}")
            await application_context.send_followup("An error occurred while purging messages.", ephemeral=True)

    @commands.slash_command(name="refresh_rules", description="Manually refresh the server rules cache.")
    async def refresh_rules(self, application_context: discord.ApplicationContext):
        """Force a refresh of the cached server rules for the current guild.

        Parameters
        ----------
        application_context:
            Slash command invocation context used to infer the target guild.
        """
        try:
            guild = application_context.guild
            if guild is None:
                raise RuntimeError("/refresh_rules can only be used inside a guild context")
            rules_text = await rules_manager.refresh_guild_rules(guild)
            
            if rules_text:
                embed = discord.Embed(
                    title="✅ Rules Cache Refreshed",
                    description=f"Successfully updated rules cache with {len(rules_text)} characters from rules channel.",
                    color=discord.Color.green(),
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                embed.add_field(
                    name="Rules Preview", 
                    value=rules_text[:500] + ("..." if len(rules_text) > 500 else ""), 
                    inline=False
                )
            else:
                embed = discord.Embed(
                    title="⚠️ No Rules Found",
                    description="No rules channel found or no content in rules channel.",
                    color=discord.Color.yellow(),
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
            
            await application_context.respond(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Failed to refresh rules for {application_context.guild.name}: {e}")
            await application_context.respond("An error occurred while refreshing rules.", ephemeral=True)

    @commands.slash_command(name="show_rules", description="Display the current cached server rules.")
    async def show_rules(self, application_context: discord.ApplicationContext):
        """Display the cached server rules to the requester as an ephemeral message.

        Parameters
        ----------
        application_context:
            Slash command invocation context used to send the response.
        """
        rules_text = guild_settings_manager.get_server_rules(application_context.guild.id)
        
        if rules_text:
            embed = discord.Embed(
                title="📋 Server Rules",
                description=rules_text[:4000],  # Discord embed description limit
                color=discord.Color.blue(),
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            embed.set_footer(text=f"Rules for {application_context.guild.name}")
            await application_context.respond(embed=embed)
        else:
            embed = discord.Embed(
                title="❌ No Rules Available",
                description="No server rules are currently cached. Try `/refresh_rules` first.",
                color=discord.Color.red(),
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            await application_context.respond(embed=embed, ephemeral=True)


def setup(discord_bot_instance):
    """Register the debug cog on the provided Discord bot instance."""
    discord_bot_instance.add_cog(DebugCog(discord_bot_instance))