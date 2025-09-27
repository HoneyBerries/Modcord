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
from modcord.configuration.guild_settings import bot_settings
from modcord.util.logger import get_logger

logger = get_logger("settings_cog")


class SettingsCog(commands.Cog):
    """Guild-level settings and toggles for AI moderation.

    The cog is intentionally small: it provides a status check, enables and
    disables AI moderation per guild, and offers a settings dump for
    operators. All changes are persisted via the bot_settings helper.
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
        enabled = bot_settings.is_ai_enabled(application_context.guild_id) if application_context.guild_id else True
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

        bot_settings.set_ai_enabled(application_context.guild_id, True)
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

        bot_settings.set_ai_enabled(application_context.guild_id, False)
        await application_context.respond("Disabled AI moderation for this server.", ephemeral=True)


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
        ai_moderation_enabled = bot_settings.is_ai_enabled(guild_id)
        server_rules = bot_settings.get_server_rules(guild_id)
        guild_settings = {
            "guild_id": guild_id,
            "ai_enabled": ai_moderation_enabled,
            "rules": server_rules,
        }
        settings_json_string = json.dumps(guild_settings, ensure_ascii=False, indent=2)
        # Keep the response ephemeral so configuration isn't exposed publicly
        await application_context.respond(f"```json\n{settings_json_string}\n```", ephemeral=True)


def setup(discord_bot_instance):
    """Register the SettingsCog with the provided bot instance."""
    discord_bot_instance.add_cog(SettingsCog(discord_bot_instance))
