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

import io
import json
from typing import Optional

import discord
from discord.ext import commands

from modcord.configuration.guild_settings import guild_settings_manager
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
        logger.info("Settings cog loaded")

    async def _ensure_guild_context(self, ctx: discord.ApplicationContext) -> bool:
        if not ctx.guild_id:
            await ctx.respond("This command can only be used in a server.", ephemeral=True)
            return False
        return True

    def _has_manage_permission(self, ctx: discord.ApplicationContext) -> bool:
        member = ctx.user
        permissions = getattr(member, "guild_permissions", None)
        return bool(getattr(permissions, "manage_guild", False))

    async def _send_settings_panel(
        self,
        ctx: discord.ApplicationContext,
        *,
        flash: Optional[str] = None,
    ) -> None:
        """Send or update the consolidated settings panel."""

        if not await self._ensure_guild_context(ctx):
            return

        if not self._has_manage_permission(ctx):
            await ctx.respond(
                "You need the Manage Server permission to configure Modcord.",
                ephemeral=True,
            )
            return

        invoker_id = getattr(ctx.user, "id", 0)
        view = GuildSettingsView(ctx.guild_id, invoker_id)
        embed = build_settings_embed(ctx.guild_id)

        await ctx.respond(content=flash, embed=embed, view=view, ephemeral=True)
        try:
            response_message = await ctx.interaction.original_response()
            view.message = response_message
        except discord.NotFound:
            view.message = None

    @commands.slash_command(name="settings", description="Open an interactive panel to configure Modcord for this server.")
    async def settings_panel(self, application_context: discord.ApplicationContext):
        """Present a consolidated settings panel backed by interactive buttons."""
        await self._send_settings_panel(application_context)

    @commands.slash_command(name="settings-dump", description="Show current per-guild settings as raw JSON. For debugging purposes.")
    async def settings_dump(self, application_context: discord.ApplicationContext):
        """Return a JSON representation of the current guild settings.

        The dump includes the guild id, whether AI moderation is enabled, and
        any stored server rules. The response is ephemeral. This command can
        only be used in a guild context.
        """
        if application_context.guild_id is None:
            await application_context.respond("This command can only be used in a server.", ephemeral=True)
            return

        guild_id = application_context.guild_id
        settings = guild_settings_manager.get_guild_settings(guild_id)
        guild_settings = {
            "guild_id": guild_id,
            "ai_enabled": settings.ai_enabled,
            "rules": settings.rules,
            "auto_actions": {
                "warn": settings.auto_warn_enabled,
                "delete": settings.auto_delete_enabled,
                "timeout": settings.auto_timeout_enabled,
                "kick": settings.auto_kick_enabled,
                "ban": settings.auto_ban_enabled,
            },
        }
        settings_json_string = json.dumps(guild_settings, ensure_ascii=False, indent=2)
        file_bytes = settings_json_string.encode("utf-8")
        file_obj = io.BytesIO(file_bytes)

        try:
            file_obj.seek(0)
            discord_file = discord.File(fp=file_obj, filename=f"guild_{guild_id}_settings.json")
            await application_context.respond(file=discord_file, ephemeral=True)
        except discord.InteractionResponded:
            # Try followup if the initial response already happened
            try:
                file_obj.seek(0)
                discord_file = discord.File(fp=file_obj, filename=f"guild_{guild_id}_settings.json")
                await application_context.followup.send(file=discord_file, ephemeral=True)
            except Exception as followup_error:
                logger.exception("Failed to send settings dump via followup: %s", followup_error)
        except Exception as e:
            logger.exception("Failed to send settings dump for guild %s: %s", guild_id, e)
            try:
                await application_context.respond("A :bug: showed up while generating the settings dump.", ephemeral=True)
            except discord.InteractionResponded:
                await application_context.followup.send("A :bug: showed up while generating the settings dump.", ephemeral=True)

    # Legacy command methods for backward compatibility with tests
    @commands.slash_command(name="ai-enable", description="Enable AI moderation for this server.")
    async def ai_enable(self, ctx: discord.ApplicationContext):
        """Enable AI moderation for the server."""
        if not await self._ensure_guild_context(ctx):
            return
        if not self._has_manage_permission(ctx):
            await ctx.respond("You need the Manage Server permission to configure Modcord.", ephemeral=True)
            return
        guild_settings_manager.set_ai_enabled(ctx.guild_id, True)
        await ctx.respond("AI moderation has been **enabled** for this server.", ephemeral=True)

    @commands.slash_command(name="ai-disable", description="Disable AI moderation for this server.")
    async def ai_disable(self, ctx: discord.ApplicationContext):
        """Disable AI moderation for the server."""
        if not await self._ensure_guild_context(ctx):
            return
        if not self._has_manage_permission(ctx):
            await ctx.respond("You need the Manage Server permission to configure Modcord.", ephemeral=True)
            return
        guild_settings_manager.set_ai_enabled(ctx.guild_id, False)
        await ctx.respond("AI moderation has been **disabled** for this server.", ephemeral=True)

    @commands.slash_command(name="ai-status", description="Check whether AI moderation is enabled for this server.")
    async def ai_status(self, ctx: discord.ApplicationContext):
        """Report whether AI moderation is enabled."""
        if not await self._ensure_guild_context(ctx):
            return
        # Build a simple embed showing AI status
        enabled = guild_settings_manager.is_ai_enabled(ctx.guild_id)
        ai_status_text = "Enabled ✅" if enabled else "Disabled ❌"
        embed = discord.Embed(
            title="AI Moderation Status",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="AI Moderation", value=ai_status_text, inline=False)
        await ctx.respond(embed=embed, ephemeral=True)

    @commands.slash_command(name="ai-set-action", description="Enable or disable a specific AI moderation action.")
    async def ai_set_action(
        self,
        ctx: discord.ApplicationContext,
        action: str,
        enabled: bool,
    ):
        """Enable or disable a specific AI action (warn, delete, timeout, kick, ban)."""
        if not await self._ensure_guild_context(ctx):
            return
        if not self._has_manage_permission(ctx):
            await ctx.respond("You need the Manage Server permission to configure Modcord.", ephemeral=True)
            return
        
        from modcord.util.moderation_datatypes import ActionType
        action_map = {
            "warn": ActionType.WARN,
            "delete": ActionType.DELETE,
            "timeout": ActionType.TIMEOUT,
            "kick": ActionType.KICK,
            "ban": ActionType.BAN,
        }
        
        action_type = action_map.get(action.lower())
        if action_type is None:
            await ctx.respond("Unsupported action.", ephemeral=True)
            return
        
        guild_settings_manager.set_action_allowed(ctx.guild_id, action_type, enabled)
        state = "enabled" if enabled else "disabled"
        await ctx.respond(f"Action '{action}' has been {state}.", ephemeral=True)


def setup(discord_bot_instance):
    """Add the settings cog to the supplied Discord bot instance."""
    discord_bot_instance.add_cog(GuildSettingsCog(discord_bot_instance))
