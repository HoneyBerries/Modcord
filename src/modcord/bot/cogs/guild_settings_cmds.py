"""
Settings cog: guild-scoped toggles for AI moderation and related settings.

This cog exposes a small set of slash commands to inspect and toggle whether
AI-powered moderation is enabled for the current guild, and to dump the
per-guild settings as JSON for debugging or auditing.

Behavior and permissions
- Commands that change state (ai_enable / ai_disable) require the invoking
  user to have the Manage Server permission.
- Status and dump commands are safe to run by any user, but their responses
  are ephemeral to avoid leaking configuration in public channels.

Quick usage example
    # In your bot setup code
    from modcord.bot.cogs.settings import SettingsCog
    bot.add_cog(SettingsCog(bot))
"""

import discord
from discord.ext import commands
import json
import io
from modcord.configuration.guild_settings import guild_settings_manager
from modcord.util.logger import get_logger
from modcord.util.moderation_models import ActionType

logger = get_logger("settings_cog")


class SettingsCog(commands.Cog):
    """Guild-level settings and toggles for AI moderation.

    The cog is intentionally small: it provides a status check, enables and
    disables AI moderation per guild, and offers a settings dump for
    operators. All changes are persisted via the guild settings manager helper.
    """

    def __init__(self, discord_bot_instance):
        self.discord_bot_instance = discord_bot_instance
        logger.info("Settings cog loaded")

    @commands.slash_command(name="ai_status", description="Show whether AI moderation is enabled in this server.")
    async def ai_status(self, application_context: discord.ApplicationContext):
        """Report whether AI moderation is enabled for this guild.

        The response is ephemeral. If run outside a guild the command reports
        a sensible default (enabled) to avoid surprising behaviour in DMs.
        """
        enabled = guild_settings_manager.is_ai_enabled(application_context.guild_id) if application_context.guild_id else True
        status = "enabled" if enabled else "disabled"
        await application_context.respond(f"AI moderation is currently {status}.", ephemeral=True)

    @commands.slash_command(name="ai_enable", description="Enable AI moderation in this server.")
    async def ai_enable(self, application_context: discord.ApplicationContext):
        """Enable AI moderation for the current guild.

        Requires the invoking user to have the Manage Server permission. The
        command replies ephemerally to confirm the change. This operation is
        a no-op when run outside a guild.
        """
        if not application_context.guild_id:
            await application_context.respond("This command can only be used in a server.", ephemeral=True)
            return

        if not application_context.user.guild_permissions.manage_guild:
            await application_context.respond("You do not have permission to change server settings (Manage Server required).", ephemeral=True)
            return

        guild_settings_manager.set_ai_enabled(application_context.guild_id, True)
        await application_context.respond("Enabled AI moderation for this server.", ephemeral=True)

    @commands.slash_command(name="ai_disable", description="Disable AI moderation in this server.")
    async def ai_disable(self, application_context: discord.ApplicationContext):
        """Disable AI moderation for the current guild.

        Requires Manage Server permission. The command replies ephemerally to
        confirm the change. This operation is a no-op when run outside a guild.
        """
        if not application_context.guild_id:
            await application_context.respond("This command can only be used in a server.", ephemeral=True)
            return

        if not application_context.user.guild_permissions.manage_guild:
            await application_context.respond("You do not have permission to change server settings (Manage Server required).", ephemeral=True)
            return

        guild_settings_manager.set_ai_enabled(application_context.guild_id, False)
        await application_context.respond("Disabled AI moderation for this server.", ephemeral=True)


    @commands.slash_command(name="ai_set_action", description="Enable or disable specific AI moderation actions.")
    @discord.option(
        "action",
        description="The moderation action to toggle",
        choices=["warn", "delete", "timeout", "kick", "ban"],
    )
    @discord.option(
        "enabled",
        description="Whether the action should be allowed",
        input_type=bool,
    )
    
    async def ai_set_action(self, application_context: discord.ApplicationContext, action: str, enabled: bool):
        """Toggle whether the AI may perform a specific action automatically."""

        if not application_context.guild_id:
            await application_context.respond("This command can only be used in a server.", ephemeral=True)
            return

        if not application_context.user.guild_permissions.manage_guild:
            await application_context.respond(
                "You do not have permission to change server settings (Manage Server required).",
                ephemeral=True,
            )
            return

        try:
            action_type = ActionType(action)
        except ValueError:
            await application_context.respond("Unsupported action.", ephemeral=True)
            return

        guild_settings_manager.set_action_allowed(application_context.guild_id, action_type, enabled)
        state = "enabled" if enabled else "disabled"
        await application_context.respond(
            f"AI {action} actions are now {state} for this server.",
            ephemeral=True,
        )


    @commands.slash_command(name="settings_dump", description="Show current per-guild settings as JSON.")
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
        # Always send the dump as a JSON file attachment to avoid message
        # length limits and ensure the response is easy to download and
        # inspect. Keep responses ephemeral so configuration isn't exposed.
        try:
            file_bytes = settings_json_string.encode("utf-8")
            file_obj = io.BytesIO(file_bytes)
            file_obj.seek(0)
            discord_file = discord.File(fp=file_obj, filename=f"guild_{guild_id}_settings.json")
            try:
                await application_context.respond(file=discord_file, ephemeral=True)
            except discord.InteractionResponded:
                # If the interaction was already responded to, use followup
                await application_context.followup.send(file=discord_file, ephemeral=True)
        except Exception as e:
            logger.exception("Failed to send settings dump for guild %s: %s", guild_id, e)
            try:
                await application_context.respond("A :bug: showed up while generating the settings dump.", ephemeral=True)
            except discord.InteractionResponded:
                await application_context.followup.send("A :bug: showed up while generating the settings dump.", ephemeral=True)


def setup(discord_bot_instance):
    """Register the SettingsCog with the provided bot instance."""
    discord_bot_instance.add_cog(SettingsCog(discord_bot_instance))
