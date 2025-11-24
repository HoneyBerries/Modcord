"""
Debug commands cog for the Discord Moderation Bot.
"""

import datetime

import discord
from discord.ext import commands

from modcord.configuration.guild_settings import guild_settings_manager
from modcord.util.logger import get_logger
from modcord.moderation.moderation_datatypes import (
    ActionData,
    ActionType,
    ModerationMessage,
    ModerationUser,
)
from modcord.util.discord_utils import apply_action_decision
from modcord.moderation.human_review_manager import HumanReviewManager

logger = get_logger("debug_commands")

class DebugCog(commands.Cog):
    """Cog for debug commands."""

    debug = discord.SlashCommandGroup("debug", "Debug commands for bot administration")

    def __init__(self, bot: discord.Bot):
        self.bot = bot

    @debug.command(name="test", description="Test command to verify the bot is responsive")
    async def test(self, application_context: discord.ApplicationContext) -> None:
        """Test command to verify the bot is responsive."""
        try:
            embed = discord.Embed(
                title="✅ Bot Test Successful",
                description="The bot is responsive and working correctly.",
                color=discord.Color.green(),
            )
            embed.add_field(name="Guild", value=application_context.guild.name, inline=False)
            embed.add_field(name="User", value=application_context.user.mention, inline=False)
            await application_context.respond(embed=embed, ephemeral=True)
            logger.debug(f"Test command executed by {application_context.user} in {application_context.guild.name}")
        except Exception as e:
            logger.error(f"Error in test command: {e}")
            await application_context.respond(content=f"❌ Error: {e}", ephemeral=True)

    @debug.command(name="purge", description="Delete all messages in the current channel")
    async def purge(self, application_context: discord.ApplicationContext) -> None:
        """Delete all messages in the current channel."""
        try:
            await application_context.defer(ephemeral=True)
            guild = application_context.guild
            channel = application_context.channel

            if not guild or not channel:
                await application_context.send_followup(content="❌ This command must be used in a guild channel.", ephemeral=True)
                return

            deleted = await channel.purge(limit=None)
            embed = discord.Embed(
                title="✅ Channel Purged",
                description=f"Deleted {len(deleted)} messages from {channel.mention}",
                color=discord.Color.green(),
            )
            await application_context.send_followup(embed=embed)
            logger.debug(f"Purged {len(deleted)} messages from {channel.name} in {guild.name}")
        except Exception as e:
            logger.error(f"Error in purge command: {e}")
            await application_context.send_followup(content=f"❌ Error: {e}", ephemeral=True)

    @debug.command(name="refresh_rules", description="Manually refresh the server rules cache")
    async def refresh_rules(self, application_context: discord.ApplicationContext) -> None:
        """Manually refresh the server rules cache from the database."""
        try:
            guild = application_context.guild

            if not guild:
                await application_context.respond(content="❌ This command must be used in a guild.", ephemeral=True)
                return

            settings = guild_settings_manager.get_guild_settings(guild.id)
            embed = discord.Embed(
                title="✅ Rules Cache Refreshed",
                description=f"Rules for {guild.name} have been refreshed from the database.",
                color=discord.Color.green(),
            )
            embed.add_field(name="Rules Length", value=str(len(settings.rules)), inline=False)
            await application_context.respond(embed=embed, ephemeral=True)
            logger.debug(f"Rules cache refreshed for guild {guild.name}")
        except Exception as e:
            logger.error(f"Error in refresh_rules command: {e}")
            await application_context.respond(content=f"❌ Error: {e}", ephemeral=True)

    @debug.command(name="show_rules", description="Display the current server rules")
    async def show_rules(self, application_context: discord.ApplicationContext) -> None:
        """Display the current server rules cached in memory."""
        try:
            guild = application_context.guild

            if not guild:
                await application_context.respond(content="❌ This command must be used in a guild.", ephemeral=True)
                return

            rules = guild_settings_manager.get_server_rules(guild.id)
            if not rules:
                embed = discord.Embed(
                    title="📋 Server Rules",
                    description="No rules have been set for this server.",
                    color=discord.Color.orange(),
                )
            else:
                embed = discord.Embed(
                    title="📋 Server Rules",
                    description=rules,
                    color=discord.Color.blue(),
                )
            await application_context.respond(embed=embed, ephemeral=True)
            logger.debug(f"Displayed rules for guild {guild.name}")
        except Exception as e:
            logger.error(f"Error in show_rules command: {e}")
            await application_context.respond(content=f"❌ Error: {e}", ephemeral=True)

    @debug.command(name="simulate_review", description="Simulate a moderation review action for testing")
    async def simulate_review(self, application_context: discord.ApplicationContext) -> None:
        """Simulate a hardcoded moderation review action to test the review notification system."""
        try:
            # Defer IMMEDIATELY to avoid interaction timeout
            await application_context.defer(ephemeral=True)
            
            guild = application_context.guild
            channel = application_context.channel
            user = application_context.user

            if not guild or not channel:
                await application_context.followup.send(content="❌ This command must be used in a guild channel.", ephemeral=True)
                return

            # Check if guild has review channels configured
            settings = guild_settings_manager.get_guild_settings(guild.id)
            if not HumanReviewManager.validate_review_channels(settings):
                await application_context.followup.send(
                    content="❌ No review channels configured for this guild. Use `/config set_review_channel` first.",
                    ephemeral=True
                )
                return

            # Check if user is a Member before we do any heavy work
            if not isinstance(user, discord.Member):
                await application_context.followup.send(content="❌ User must be a guild member.", ephemeral=True)
                return

            # Create a fake message for the review
            fake_message = await channel.send("🔨 **[DEBUG]** This is a simulated violation message for testing. It contains potentially problematic content that the AI would flag for review.")
            
            # Create hardcoded ActionData simulating AI output
            action_data = ActionData(
                user_id=str(user.id),
                action=ActionType.REVIEW,
                reason="Simulated review: Message contains ambiguous content that requires human moderator judgment. The AI is uncertain whether this violates server rules.",
                message_ids=[str(fake_message.id)],
                timeout_duration=0,
                ban_duration=0
            )

            pivot_message = ModerationMessage(
                message_id=str(fake_message.id),
                user_id=str(user.id),
                content=fake_message.content,
                timestamp=fake_message.created_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                guild_id=guild.id,
                channel_id=channel.id if hasattr(channel, "id") else None,
                discord_message=fake_message,
            )

            moderator_roles = [role.name for role in user.roles] if isinstance(user, discord.Member) else []
            join_date = None
            if isinstance(user, discord.Member) and user.joined_at:
                join_date = (
                    user.joined_at.astimezone(datetime.timezone.utc)
                    .replace(microsecond=0)
                    .isoformat()
                    .replace("+00:00", "Z")
                )

            review_user = ModerationUser(
                user_id=str(user.id),
                username=str(user),
                roles=moderator_roles,
                join_date=join_date,
                messages=[pivot_message],
                past_actions=[],
            )

            # Initialize HumanReviewManager
            review_manager = HumanReviewManager(self.bot)
            
            # Add review item to the manager (user-centric, no pivot_message parameter)
            await review_manager.add_item_for_review(
                guild=guild,
                user=review_user,
                action=action_data
            )
            
            # Finalize the batch to send the review notification
            success = await review_manager.send_review_embed(guild, settings)
            
            if success:
                embed = discord.Embed(
                    title="✅ Review Simulation Complete",
                    description="A simulated review notification has been sent to configured review channels.",
                    color=discord.Color.green(),
                )
                embed.add_field(name="Action", value="REVIEW", inline=True)
                embed.add_field(name="Target User", value=user.mention, inline=True)
                embed.add_field(name="Test Message", value=f"[Message {fake_message.id}]({fake_message.jump_url})", inline=False)
                
                # List review channels
                channel_mentions = []
                for channel_id in settings.review_channel_ids:
                    review_channel = guild.get_channel(channel_id)
                    if review_channel:
                        channel_mentions.append(review_channel.mention)
                
                if channel_mentions:
                    embed.add_field(name="Review Channels", value=", ".join(channel_mentions), inline=False)
                
                await application_context.followup.send(embed=embed, ephemeral=True)
                logger.info(f"Simulated review action executed by {user} ({user.display_name}) in {guild.name}")
            else:
                await application_context.followup.send(content="❌ Failed to send review notification.", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error in simulate_review command: {e}")
            import traceback
            traceback.print_exc()
            
            # Try to send error message - if defer failed, this will also fail but at least we logged it
            try:
                await application_context.followup.send(content=f"❌ Error: {e}", ephemeral=True)
            except Exception:
                logger.error("Failed to send error message to user - interaction may have timed out")


def setup(bot: discord.Bot) -> None:
    """Register the debug cog and command group with the bot."""
    bot.add_cog(DebugCog(bot))