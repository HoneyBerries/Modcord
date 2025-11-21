"""
Settings cog: guild-scoped toggles for AI moderation and related settings.

This cog exposes two slash commands:
- /settings: Interactive panel with buttons to configure AI moderation
- /settings_dump: Export current settings as JSON for debugging

All settings changes require the Manage Server permission.
Responses are ephemeral to avoid leaking configuration in public channels.

Quick usage example
    # In your bot setup code
    from modcord.bot.cogs.guild_settings_cmds import SettingsCog
    bot.add_cog(GuildSettingsCog(bot))
"""


import discord
from discord.ext import commands

from modcord.util.logger import get_logger
from modcord.ui.guild_settings_ui import build_settings_embed, GuildSettingsView

logger = get_logger("settings_cog")


class GuildSettingsCog(commands.Cog):
    """Guild-level settings and toggles for AI moderation.

    Provides an interactive button-based settings panel and a JSON dump command
    for debugging. All changes are persisted via the guild settings manager.
    """

    def __init__(self, discord_bot_instance):
        """Store the Discord bot reference and prepare guild settings access."""
        self.discord_bot_instance = discord_bot_instance
        logger.info("[GUILD SETTINGS CMDS] Settings cog loaded")

    async def _ensure_guild_context(self, ctx: discord.ApplicationContext) -> bool:
        if not ctx.guild_id:
            await ctx.defer(ephemeral=True)
            await ctx.send_followup("This command can only be used in a server.")
            return False
        return True

    def _has_manage_permission(self, ctx: discord.ApplicationContext) -> bool:
        member = ctx.user
        permissions = member.guild_permissions
        return bool(permissions.manage_guild)


    @commands.slash_command(name="settings", description="Open an interactive panel to configure Modcord for this server.")
    async def settings_panel(self, ctx: discord.ApplicationContext):
        """Present a consolidated settings panel backed by interactive buttons."""
        if not await self._ensure_guild_context(ctx):
            return

        if not self._has_manage_permission(ctx):
            await ctx.defer(ephemeral=True)
            await ctx.send_followup(
                "You need the Manage Server permission to configure Modcord."
            )
            return

        invoker_id = ctx.user.id
        view = GuildSettingsView(ctx.guild_id, invoker_id)
        embed = build_settings_embed(ctx.guild_id)

        await ctx.defer(ephemeral=True)
        await ctx.send_followup(embed=embed, view=view)
        try:
            response_message = await ctx.interaction.original_response()
            view.message = response_message
        except discord.NotFound:
            view.message = None


def setup(discord_bot_instance):
    """Add the settings cog to the supplied Discord bot instance."""
    discord_bot_instance.add_cog(GuildSettingsCog(discord_bot_instance))