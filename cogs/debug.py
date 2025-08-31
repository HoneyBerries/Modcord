"""
Debug commands cog for the Discord Moderation Bot.
"""

import datetime

import discord
from discord.ext import commands

from logger import get_logger
import bot_helper
from bot_config import bot_config

logger = get_logger("debug_cog")


class DebugCog(commands.Cog):
    """
    Cog containing debugging and administrative commands.
    """
    
    def __init__(self, bot):
        self.bot = bot
        logger.info("Debug cog loaded")

    @commands.slash_command(name="refresh_rules", description="Manually refresh the server rules cache.")
    @commands.has_permissions(administrator=True)
    async def refresh_rules(self, ctx: discord.ApplicationContext):
        """Manually refresh the server rules cache for this guild."""
        await ctx.defer()
        
        try:
            rules_text = await bot_helper.fetch_server_rules_from_channel(ctx.guild)
            bot_config.set_server_rules(ctx.guild.id, rules_text)
            
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
            
            await ctx.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Failed to refresh rules for {ctx.guild.name}: {e}")
            await ctx.followup.send("An error occurred while refreshing rules.", ephemeral=True)

    @commands.slash_command(name="show_rules", description="Display the current cached server rules.")
    async def show_rules(self, ctx: discord.ApplicationContext):
        """Display the current cached server rules."""
        rules_text = bot_config.get_server_rules(ctx.guild.id)
        
        if rules_text:
            embed = discord.Embed(
                title="📋 Server Rules",
                description=rules_text[:4000],  # Discord embed description limit
                color=discord.Color.blue(),
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            embed.set_footer(text=f"Rules for {ctx.guild.name}")
            await ctx.respond(embed=embed)
        else:
            embed = discord.Embed(
                title="❌ No Rules Available",
                description="No server rules are currently cached. Try `/refresh_rules` first.",
                color=discord.Color.red(),
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            await ctx.respond(embed=embed, ephemeral=True)


def setup(bot):
    """Setup function for the cog."""
    bot.add_cog(DebugCog(bot))