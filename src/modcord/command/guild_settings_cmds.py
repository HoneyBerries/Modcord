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
from modcord.configuration.guild_settings import guild_settings_manager

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
        """Ensure the command is used in a guild context."""
        if not ctx.guild_id:
            await ctx.defer(ephemeral=True)
            await ctx.send_followup("This command can only be used in a server.")
            return False
        return True

    def _has_manage_permission(self, ctx: discord.ApplicationContext) -> bool:
        """Check if the user has Manage Server permission."""
        member = ctx.user
        permissions = member.guild_permissions
        return bool(permissions.manage_guild)
    
    async def _check_permissions(self, ctx: discord.ApplicationContext) -> bool:
        """Check both guild context and manage permissions. Returns True if all checks pass."""
        if not await self._ensure_guild_context(ctx):
            return False
        if not self._has_manage_permission(ctx):
            await ctx.respond("You need Manage Server permission.", ephemeral=True)
            return False
        return True

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

    # Subcommand group for moderator settings
    mods = discord.SlashCommandGroup("mods", "Manage moderator settings for AI reviews")

    @mods.command(name="add-role", description="Add a role to receive AI review alerts")
    async def add_mod_role(self, ctx: discord.ApplicationContext, role: discord.Role):
        if not await self._check_permissions(ctx):
            return
        
        settings = guild_settings_manager.get_guild_settings(ctx.guild_id)
        if role.id not in settings.moderator_role_ids:
            settings.moderator_role_ids.append(role.id)
            guild_settings_manager._trigger_persist(ctx.guild_id)
            await ctx.respond(f"✅ Added {role.mention} to moderator roles.", ephemeral=True)
        else:
            await ctx.respond(f"{role.mention} is already a moderator role.", ephemeral=True)

    @mods.command(name="remove-role", description="Remove a role from receiving AI review alerts")
    async def remove_mod_role(self, ctx: discord.ApplicationContext, role: discord.Role):
        if not await self._check_permissions(ctx):
            return
        
        settings = guild_settings_manager.get_guild_settings(ctx.guild_id)
        if role.id in settings.moderator_role_ids:
            settings.moderator_role_ids.remove(role.id)
            guild_settings_manager._trigger_persist(ctx.guild_id)
            await ctx.respond(f"✅ Removed {role.mention} from moderator roles.", ephemeral=True)
        else:
            await ctx.respond(f"{role.mention} is not a moderator role.", ephemeral=True)

    @mods.command(name="add-channel", description="Add a channel to receive AI review alerts")
    async def add_review_channel(self, ctx: discord.ApplicationContext, channel: discord.TextChannel):
        if not await self._check_permissions(ctx):
            return
        
        settings = guild_settings_manager.get_guild_settings(ctx.guild_id)
        if channel.id not in settings.review_channel_ids:
            settings.review_channel_ids.append(channel.id)
            guild_settings_manager._trigger_persist(ctx.guild_id)
            await ctx.respond(f"✅ Added {channel.mention} to review channels.", ephemeral=True)
        else:
            await ctx.respond(f"{channel.mention} is already a review channel.", ephemeral=True)

    @mods.command(name="remove-channel", description="Remove a channel from receiving AI review alerts")
    async def remove_review_channel(self, ctx: discord.ApplicationContext, channel: discord.TextChannel):
        if not await self._check_permissions(ctx):
            return
        
        settings = guild_settings_manager.get_guild_settings(ctx.guild_id)
        if channel.id in settings.review_channel_ids:
            settings.review_channel_ids.remove(channel.id)
            guild_settings_manager._trigger_persist(ctx.guild_id)
            await ctx.respond(f"✅ Removed {channel.mention} from review channels.", ephemeral=True)
        else:
            await ctx.respond(f"{channel.mention} is not a review channel.", ephemeral=True)

    @mods.command(name="list", description="List current moderator settings")
    async def list_mods(self, ctx: discord.ApplicationContext):
        if not await self._check_permissions(ctx):
            return
        
        settings = guild_settings_manager.get_guild_settings(ctx.guild_id)
        
        roles = [f"<@&{rid}>" for rid in settings.moderator_role_ids]
        channels = [f"<#{cid}>" for cid in settings.review_channel_ids]
        
        embed = discord.Embed(title="Moderator Settings", color=discord.Color.blue())
        embed.add_field(name="Moderator Roles", value=", ".join(roles) or "None", inline=False)
        embed.add_field(name="Review Channels", value=", ".join(channels) or "None (reviews disabled)", inline=False)
        embed.set_footer(text="Add roles and channels manually to configure review notifications.")
        
        await ctx.respond(embed=embed, ephemeral=True)


def setup(discord_bot_instance):
    """Add the settings cog to the supplied Discord bot instance."""
    discord_bot_instance.add_cog(GuildSettingsCog(discord_bot_instance))