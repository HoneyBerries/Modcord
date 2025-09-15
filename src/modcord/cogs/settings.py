"""
Settings commands cog for toggling AI moderation per guild.
"""

import discord
from discord.ext import commands

from modcord.bot_config import bot_config
from modcord.logger import get_logger

logger = get_logger("settings_cog")


class SettingsCog(commands.Cog):
    """Guild-level settings and toggles."""

    def __init__(self, discord_bot_instance):
        self.discord_bot_instance = discord_bot_instance
        logger.info("Settings cog loaded")

    @commands.slash_command(name="ai_status", description="Show whether AI moderation is enabled in this server.")
    async def ai_status(self, application_context: discord.ApplicationContext):
        enabled = bot_config.is_ai_enabled(application_context.guild_id) if application_context.guild_id else True
        status = "enabled" if enabled else "disabled"
        await application_context.respond(f"AI moderation is currently {status}.", ephemeral=True)

    @commands.slash_command(name="ai_enable", description="Enable AI moderation in this server.")
    async def ai_enable(self, application_context: discord.ApplicationContext):
        if not application_context.user.guild_permissions.manage_guild:
            await application_context.respond("You need Manage Server permission to change this setting.", ephemeral=True)
            return
        if application_context.guild_id is None:
            await application_context.respond("This command can only be used in a server.", ephemeral=True)
            return
        bot_config.set_ai_enabled(application_context.guild_id, True)
        await application_context.respond("Enabled AI moderation for this server.", ephemeral=True)

    @commands.slash_command(name="ai_disable", description="Disable AI moderation in this server.")
    async def ai_disable(self, application_context: discord.ApplicationContext):
        if not application_context.user.guild_permissions.manage_guild:
            await application_context.respond("You need Manage Server permission to change this setting.", ephemeral=True)
            return
        if application_context.guild_id is None:
            await application_context.respond("This command can only be used in a server.", ephemeral=True)
            return
        bot_config.set_ai_enabled(application_context.guild_id, False)
        await application_context.respond("Disabled AI moderation for this server.", ephemeral=True)

    @commands.slash_command(name="settings_dump", description="Show current per-guild settings as JSON.")
    async def settings_dump(self, application_context: discord.ApplicationContext):
        """Show current per-guild settings (AI and rules) as JSON."""
        if application_context.guild_id is None:
            await application_context.respond("This command can only be used in a server.", ephemeral=True)
            return
        guild_id = application_context.guild_id
        ai_moderation_enabled = bot_config.is_ai_enabled(guild_id)
        server_rules = bot_config.get_server_rules(guild_id)
        import json
        guild_settings = {
            "guild_id": guild_id,
            "ai_enabled": ai_moderation_enabled,
            "rules": server_rules,
        }
        settings_json_string = json.dumps(guild_settings, ensure_ascii=False, indent=2)
        await application_context.respond(f"```json\n{settings_json_string}\n```", ephemeral=True)


def setup(discord_bot_instance):
    discord_bot_instance.add_cog(SettingsCog(discord_bot_instance))
