"""
Debug commands cog for the Discord Moderation Bot.
"""

import datetime

import discord
from discord.ext import commands

from modcord.datatypes.discord_datatypes import GuildID
from modcord.settings.guild_settings_manager import guild_settings_manager
from modcord.util.discord import collector
from modcord.util.logger import get_logger

logger = get_logger("debug_commands")

class DebugCog(commands.Cog):
    """Cog for debug commands."""

    debug = discord.SlashCommandGroup("debug", "Debug commands for bot administration")

    def __init__(self, bot: discord.Bot):
        self.bot = bot

    @debug.command(name="test", description="Test console to verify the bot is responsive")
    async def test(self, application_context: discord.ApplicationContext) -> None:
        """Test console to verify the bot is responsive."""
        await application_context.respond(f"Bot is online at {datetime.datetime.now():.0f}, lagging behind by {self.bot.latency * 1000:.2f} ms!", ephemeral=True)


    @debug.command(name="purge", description="Delete all messages in the current channel")
    async def purge(self, application_context: discord.ApplicationContext) -> None:
        """Delete all messages in the current channel."""
        await application_context.defer(ephemeral=True)

        # Ensure the console is used in a guild channel
        guild = application_context.guild
        channel = application_context.channel

        if not guild or not channel:
            await application_context.send_followup(content="❌ This console must be used in a guild channel.", ephemeral=True)
            return

        if not isinstance(channel, discord.TextChannel | discord.VoiceChannel):
            await application_context.send_followup(content="❌ This console cannot be safely used here.", ephemeral=True)
            return
        
        new_channel = await channel.clone()

        # Delete old channel
        await channel.delete()

        # Send confirmation in the new channel and auto-delete after 10 seconds
        await new_channel.send(content=f"Channel {new_channel.mention} has been purged. This message with self-destruct in 10 seconds.", delete_after=10)





    @debug.command(name="refresh_rules", description="Manually refresh the server rules cache")
    async def refresh_rules(self, application_context: discord.ApplicationContext) -> None:
        """Manually refresh the server rules cache from the rules channel."""
        await application_context.defer(ephemeral=True)

        guild = application_context.guild
        # Null safety check - should never be null in a guild console, but just in case
        if not guild:
            await application_context.send_followup(
                content="This console must be used in a guild.",
                ephemeral=True
            )
            return

        rules_text = await collector.collect_rules(guild)
        settings = await guild_settings_manager.update(GuildID(guild.id), rules=rules_text)

        await self._respond_rules_followup(application_context, settings.rules, f"Rules cache refreshed for {guild.name}")


    @debug.command(name="show_rules", description="Display the current server rules")
    async def show_rules(self, application_context: discord.ApplicationContext) -> None:
        guild = application_context.guild

        if not guild:
            await application_context.respond(content="This console must be used in a guild.", ephemeral=True)
            return

        rules = await guild_settings_manager.get_rules(GuildID(guild.id))

        await self._respond_rules(application_context, rules, "Current rules")


    # Helper function for sending the rules response, used by both refresh_rules and show_rules
    async def _respond_rules(
        self,
        application_context: discord.ApplicationContext,
        rules: str | None,
        header: str
    ) -> None:
        """Shared helper to respond with rules."""
        if not rules:
            await application_context.respond(
                content="No rules set.",
                ephemeral=True
            )
            return

        trimmed_rules = rules[:1000] + "... (truncated)" if len(rules) > 1000 else rules

        await application_context.respond(
            content=(
                f"{header}\n\n"
                f"Length: {len(rules)} chars\n\n"
                f"{trimmed_rules}"
            ),
            ephemeral=True
        )

    async def _respond_rules_followup(
        self,
        application_context: discord.ApplicationContext,
        rules: str | None,
        header: str
    ) -> None:
        """Shared helper to respond with rules using followup."""
        if not rules:
            await application_context.send_followup(
                content="No rules set.",
                ephemeral=True
            )
            return

        trimmed_rules = rules[:1000] + "... (truncated)" if len(rules) > 1000 else rules

        await application_context.send_followup(
            content=(
                f"{header}\n\n"
                f"Length: {len(rules)} chars\n\n"
                f"{trimmed_rules}"
            ),
            ephemeral=True
        )




# Setup function to register the cog with the bot
def setup(bot: discord.Bot) -> None:
    """Register the debug cog and console group with the bot."""
    bot.add_cog(DebugCog(bot))