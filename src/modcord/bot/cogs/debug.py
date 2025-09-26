"""
Debug commands cog for the Discord Moderation Bot.
"""

import datetime

import discord
from discord.ext import commands

import modcord.bot.bot_helper as bot_helper
from modcord.bot.bot_settings import bot_settings
from modcord.util.logger import get_logger

logger = get_logger("debug_cog")


class DebugCog(commands.Cog):
    """
    Cog containing debugging and administrative commands.
    """
    
    def __init__(self, discord_bot_instance):
        self.discord_bot_instance = discord_bot_instance
        logger.info("Debug cog loaded")

    @commands.slash_command(
        name="test",
        description="Checks if the bot is online and its round trip time."
    )
    async def test(self, application_context: discord.ApplicationContext):
        """
        A simple health-check command to verify bot status and round trip time.
        """
        latency_milliseconds = self.discord_bot_instance.latency * 1000
        await application_context.respond(
            f":white_check_mark: I am online and working!\n"
            f"**Round Trip Time**: {latency_milliseconds:.2f} ms.",
            ephemeral=True
        )


    @commands.slash_command(name="refresh_rules", description="Manually refresh the server rules cache.")
    @commands.has_permissions(manage_serrver=True)
    async def refresh_rules(self, application_context: discord.ApplicationContext):
        """Manually refresh the server rules cache for this guild."""       
        try:
            rules_text = await bot_helper.fetch_server_rules_from_channel(application_context.guild)
            bot_settings.set_server_rules(application_context.guild.id, rules_text)
            
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
            logger.error(f"Failed to refresh rules for {application_context.guild.name}: {e}", exc_info=True)
            await application_context.respond("An error occurred while refreshing rules.", ephemeral=True)

    @commands.slash_command(name="show_rules", description="Display the current cached server rules.")
    async def show_rules(self, application_context: discord.ApplicationContext):
        """Display the current cached server rules."""
        rules_text = bot_settings.get_server_rules(application_context.guild.id)
        
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
    """Setup function for the cog."""
    discord_bot_instance.add_cog(DebugCog(discord_bot_instance))