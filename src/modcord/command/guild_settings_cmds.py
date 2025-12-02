"""
Settings cog: guild-scoped configuration for AI moderation.

This cog exposes two slash commands:
- /setup: Initial bot configuration (AI toggles + rules channel) using paginated UI
- /settings: Full settings panel (AI toggles + rules channel + review config) using paginated UI

All settings changes require the Manage Server permission.
Responses are ephemeral to avoid leaking configuration in public channels.
"""

import discord
from discord.ext import commands

from modcord.util.logger import get_logger
from modcord.ui.settings_pages import create_setup_paginator, create_settings_paginator
from modcord.settings.guild_settings_manager import guild_settings_manager
from modcord.datatypes.discord_datatypes import GuildID

logger = get_logger("settings_cog")


class GuildSettingsCog(commands.Cog):
    """Guild-level settings and toggles for AI moderation.

    Provides paginated setup and settings panels for configuring
    AI moderation, rules channel, and review settings.
    """

    def __init__(self, discord_bot_instance):
        """Store the Discord bot reference and prepare guild settings access."""
        self.discord_bot_instance = discord_bot_instance
        logger.info("[GUILD SETTINGS CMDS] Settings cog loaded")

    async def _ensure_guild_context(self, ctx: discord.ApplicationContext) -> bool:
        """Ensure the command is used in a guild context."""
        if not ctx.guild_id:
            await ctx.respond("This command can only be used in a server.", ephemeral=True)
            return False
        return True

    def _has_manage_permission(self, ctx: discord.ApplicationContext) -> bool:
        """Check if the user has Manage Server permission."""
        member = ctx.user
        if hasattr(member, "guild_permissions"):
            return bool(member.guild_permissions.manage_guild)
        return False

    async def _check_permissions(self, ctx: discord.ApplicationContext) -> bool:
        """Check both guild context and manage permissions. Returns True if all checks pass."""
        if not await self._ensure_guild_context(ctx):
            return False
        if not self._has_manage_permission(ctx):
            await ctx.respond("You need Manage Server permission.", ephemeral=True)
            return False
        return True

    @commands.slash_command(
        name="setup",
        description="Initial setup wizard for Modcord - configure AI moderation and rules channel."
    )
    async def setup_command(self, ctx: discord.ApplicationContext):
        """
        Launch the setup wizard for initial bot configuration.
        
        Pages:
        1. Moderation Settings (AI toggle + action toggles)
        2. Rules Channel Selection
        """
        if not await self._check_permissions(ctx):
            return

        guild_id = GuildID.from_int(ctx.guild_id)
        invoker_id = ctx.user.id

        paginator = create_setup_paginator(guild_id, invoker_id)
        await paginator.respond(ctx.interaction, ephemeral=True)

    @commands.slash_command(
        name="settings",
        description="Open the full settings panel to configure Modcord for this server."
    )
    async def settings_command(self, ctx: discord.ApplicationContext):
        """
        Launch the full settings panel.
        
        Pages:
        1. Moderation Settings (AI toggle + action toggles)
        2. Rules Channel Selection
        3. Review Settings (channels + roles)
        """
        if not await self._check_permissions(ctx):
            return

        guild_id = GuildID.from_int(ctx.guild_id)
        invoker_id = ctx.user.id

        paginator = create_settings_paginator(guild_id, invoker_id)
        await paginator.respond(ctx.interaction, ephemeral=True)


def setup(discord_bot_instance):
    """Add the settings cog to the supplied Discord bot instance."""
    discord_bot_instance.add_cog(GuildSettingsCog(discord_bot_instance))