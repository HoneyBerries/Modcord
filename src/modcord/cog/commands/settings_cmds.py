"""
Settings cog: guild-scoped toggles for AI moderation and related settings.

This cog exposes two slash commands:
- /settings: Interactive panel with buttons to configure AI moderation
- /settings_dump: Export current settings as JSON for debugging

All settings changes require the Manage Server permission.
Responses are ephemeral to avoid leaking configuration in public channels.
"""
import io
import json

import discord
from discord.ext import commands

from modcord.datatypes.discord_datatypes import GuildID
from modcord.settings.guild_settings_manager import guild_settings_manager
from modcord.ui.guild_settings_ui import build_full_settings_embed, FullSettingsView
from modcord.util.logger import get_logger

logger = get_logger("settings_commands")


class GuildSettingsCog(commands.Cog):
    """Guild-level settings and toggles for AI moderation."""

    def __init__(self, discord_bot_instance):
        self.discord_bot_instance = discord_bot_instance
        logger.info("[GUILD SETTINGS CMDS] Settings cog loaded")

    async def _ensure_guild_context(self, ctx: discord.ApplicationContext) -> bool:
        if not ctx.guild_id:
            await ctx.defer(ephemeral=True)
            await ctx.send_followup("This console can only be used in a server.")
            return False
        return True

    def _has_manage_permission(self, ctx: discord.ApplicationContext) -> bool:
        if not isinstance(ctx.user, discord.Member):
            return False
        return ctx.user.guild_permissions.manage_guild

    async def _check_permissions(self, ctx: discord.ApplicationContext) -> bool:
        if not await self._ensure_guild_context(ctx):
            return False
        if not self._has_manage_permission(ctx):
            await ctx.respond("You need Manage Server permission.", ephemeral=True)
            return False
        return True


    @commands.slash_command(
        name="settings",
        description="Open an interactive panel to configure Modcord for this server.",
    )
    async def settings_panel(self, ctx: discord.ApplicationContext):
        """Send a single embed with all settings and interactive buttons."""
        if not await self._check_permissions(ctx):
            return

        guild_id = GuildID(ctx.guild_id)
        settings = await guild_settings_manager.get_settings(guild_id)

        embed = build_full_settings_embed(settings)
        view = FullSettingsView(guild_id, settings)

        await ctx.respond(embed=embed, view=view, ephemeral=True)

    @commands.slash_command(
        name="settings_dump",
        description="Export current guild settings as a .txt file (debug only).",
    )
    async def settings_dump(self, ctx: discord.ApplicationContext):
        if not await self._check_permissions(ctx):
            return

        guild_id = GuildID(ctx.guild_id)
        settings = await guild_settings_manager.get_settings(guild_id)

        # Convert settings to JSON string
        json_dump = settings.dict() if hasattr(settings, "dict") else str(settings)
        json_str = json.dumps(json_dump, indent=2) if isinstance(json_dump, dict) else str(json_dump)

        # Create an in-memory file
        file_buffer = io.BytesIO(json_str.encode("utf-8"))
        file_buffer.seek(0)
        discord_file = discord.File(fp=file_buffer, filename=f"guild_{guild_id}_settings.txt")

        await ctx.respond(
            content="Here is the current guild settings:",
            file=discord_file,
            ephemeral=True
        )

def setup(discord_bot_instance):
    discord_bot_instance.add_cog(GuildSettingsCog(discord_bot_instance))
