"""
Settings commands cog for toggling AI moderation per guild.
"""

import discord
from discord.ext import commands

from ..logger import get_logger
from ..bot_config import bot_config

logger = get_logger("settings_cog")


class SettingsCog(commands.Cog):
    """Guild-level settings and toggles."""

    def __init__(self, discord_bot_instance):
        self.discord_bot_instance = discord_bot_instance
        logger.info("Settings cog loaded")

    @commands.slash_command(name="ai_status", description="Show whether AI moderation is enabled in this server.")
    async def ai_status(self, ctx: discord.ApplicationContext):
        enabled = bot_config.is_ai_enabled(ctx.guild_id) if ctx.guild_id else True
        status = "enabled" if enabled else "disabled"
        await ctx.respond(f"AI moderation is currently {status}.", ephemeral=True)

    @commands.slash_command(name="ai_enable", description="Enable AI moderation in this server.")
    async def ai_enable(self, ctx: discord.ApplicationContext):
        if not ctx.user.guild_permissions.manage_guild:
            await ctx.respond("You need Manage Server permission to change this setting.", ephemeral=True)
            return
        if ctx.guild_id is None:
            await ctx.respond("This command can only be used in a server.", ephemeral=True)
            return
        bot_config.set_ai_enabled(ctx.guild_id, True)
        await ctx.respond("Enabled AI moderation for this server.", ephemeral=True)

    @commands.slash_command(name="ai_disable", description="Disable AI moderation in this server.")
    async def ai_disable(self, ctx: discord.ApplicationContext):
        if not ctx.user.guild_permissions.manage_guild:
            await ctx.respond("You need Manage Server permission to change this setting.", ephemeral=True)
            return
        if ctx.guild_id is None:
            await ctx.respond("This command can only be used in a server.", ephemeral=True)
            return
        bot_config.set_ai_enabled(ctx.guild_id, False)
        await ctx.respond("Disabled AI moderation for this server.", ephemeral=True)

    @commands.slash_command(name="settings_dump", description="Show current per-guild settings as JSON.")
    async def settings_dump(self, ctx: discord.ApplicationContext):
        """Show current per-guild settings (AI and rules) as JSON."""
        if ctx.guild_id is None:
            await ctx.respond("This command can only be used in a server.", ephemeral=True)
            return
        gid = ctx.guild_id
        ai_enabled = bot_config.is_ai_enabled(gid)
        rules = bot_config.get_server_rules(gid)
        import json
        settings = {
            "guild_id": gid,
            "ai_enabled": ai_enabled,
            "rules": rules,
        }
        json_str = json.dumps(settings, ensure_ascii=False, indent=2)
        await ctx.respond(f"```json\n{json_str}\n```", ephemeral=True)


def setup(discord_bot_instance):
    discord_bot_instance.add_cog(SettingsCog(discord_bot_instance))
