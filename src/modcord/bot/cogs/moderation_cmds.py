"""
Moderation cog: commands for taking disciplinary actions on server members.

This module provides a small collection of slash commands that a moderator
can use to warn, timeout, kick, or ban users. The commands are implemented as
methods on ModerationActionCog and rely on helper utilities in
modcord.bot.bot_helper for common tasks (permission checks, duration parsing,
scheduling unbans, DM/embeds, and background message deletion).

Design notes and expectations
- Commands perform standard safety checks (bot permission, target is a
  guild member, self-moderation prevention, and administrator protection).
- Reason strings, optional durations, and message-deletion windows are
  supported where applicable. Long-running tasks (delete messages) are
  scheduled in the background to avoid blocking the command response.
- Errors are routed to bot_helper.handle_error to provide consistent
  operator-visible logs and user-facing fallback messaging.

Quick usage example
    # In your bot setup code
    from modcord.bot.cogs.moderation import ModerationActionCog
    bot.add_cog(ModerationActionCog(bot))

Permissions
- Each command checks for the appropriate moderator permission before
  executing. If the permission check fails the command replies
  ephemerally to the invoking user.
"""

import asyncio
import datetime
from typing import Optional

import discord
from discord import Option
from discord.ext import commands

from modcord.util.discord_utils import (
    has_permissions,
    parse_duration_to_seconds,
    PERMANENT_DURATION,
    send_dm_and_embed,
    delete_messages_background,
    DURATION_CHOICES,
    DELETE_MESSAGE_CHOICES,
)
from modcord.bot.unban_scheduler import schedule_unban
from modcord.util.moderation_models import ActionType
from modcord.util.logger import get_logger

logger = get_logger("moderation_cog")


class ModerationActionCog(commands.Cog):
    """Cog containing moderation-related slash commands.

    Each command defers its response and performs a common permission and
    validation sequence before delegating to handle_moderation_command which
    implements the action-specific behavior (timeout, kick, ban, warn).

    The cog expects a bot helper module for common utilities; the instance
    passed into the cog is used for scheduling tasks that require the bot
    instance (for example, scheduling an unban).
    """

    def __init__(self, discord_bot_instance):
        self.discord_bot_instance = discord_bot_instance
        logger.info("Moderation cog loaded")

    async def check_moderation_permissions(
        self, 
        application_context: discord.ApplicationContext, 
        target_user: discord.Member,
        required_permission_name: str
    ) -> bool:
        """Run shared pre-checks for moderation commands.

        This helper centralizes the common checks performed before executing
        a moderation action. It sends ephemeral responses for expected
        failures so callers can simply return when False is returned.

        Args:
            application_context: The ApplicationContext for the invoking user.
            target_user: The Member to act on.
            required_permission_name: The permission name to verify on the
                invoking user (e.g., 'moderate_members', 'kick_members').

        Returns:
            True when all checks pass and the caller may proceed with the
            moderation action; False when an ephemeral response has been
            sent to the invoker indicating why the action cannot proceed.
        """
        # Check invoking user's permission
        if not has_permissions(application_context, **{required_permission_name: True}):
            await application_context.respond("You do not have permission to use this command.", ephemeral=True)
            return False

        # Check if target is a member of this server
        if not isinstance(target_user, discord.Member):
            await application_context.respond("The specified user is not a member of this server.", ephemeral=True)
            return False

        # Prevent self-moderation
        if target_user.id == application_context.user.id:
            await application_context.respond("You cannot perform moderation actions on yourself.", ephemeral=True)
            return False

        # Protect administrators from moderation via these commands
        if target_user.guild_permissions.administrator:
            await application_context.respond("You cannot perform moderation actions against administrators.", ephemeral=True)
            return False

        return True

    async def handle_moderation_command(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Member,
        action_type: ActionType,
        reason: str,
        duration: Optional[str] = None,
        delete_message_seconds: int = 0
    ) -> None:
        """Execute a moderation action and perform follow-up tasks.

        This function contains the core implementation shared by the
        moderation commands. It applies the requested action, sends a DM and
        embed to notify the user, and optionally schedules background
        message deletion or an unban for temporary bans.

        Args:
            ctx: The command context (used for guild/channel references).
            user: The Member the action targets.
            action_type: The ActionType enum value indicating the action.
            reason: A human-readable reason stored with the action.
            duration: Optional duration string for timeouts or temporary bans.
            delete_message_seconds: If > 0, how many seconds of the user's
                recent messages to delete (handled asynchronously).

        Notes:
            - Any raised exceptions are forwarded to bot_helper.handle_error
              so the bot has a single error reporting pathway.
        """
        try:            
            # Perform the specific action
            if action_type == ActionType.TIMEOUT and duration:
                duration_seconds = parse_duration_to_seconds(duration)
                until = discord.utils.utcnow() + datetime.timedelta(seconds=duration_seconds)
                await user.timeout(until, reason=reason)
                
            elif action_type == ActionType.KICK:
                await user.kick(reason=reason)

            elif action_type == ActionType.BAN:
                await ctx.guild.ban(user, reason=reason)

                if duration and duration != PERMANENT_DURATION:
                    duration_seconds = parse_duration_to_seconds(duration)
                    logger.info(f"Scheduling unban for {user.display_name} in {duration_seconds} seconds.")
                    await schedule_unban(
                        guild=ctx.guild,
                        user_id=user.id,
                        channel=ctx.channel,
                        duration_seconds=duration_seconds,
                        bot=self.discord_bot_instance,
                    )
            
            # Send DM and embed
            await send_dm_and_embed(ctx, user, action_type, reason, duration)
            
            # Delete messages in background if requested
            if delete_message_seconds > 0:
                asyncio.create_task(delete_messages_background(ctx, user, delete_message_seconds))
                
        except Exception as e:
            logger.exception("Error handling moderation command: %s", e)
            try:
                await ctx.respond("An error occurred while processing the command.", ephemeral=True)
            except Exception:
                try:
                    await ctx.followup.send("An error occurred while processing the command.", ephemeral=True)
                except Exception:
                    logger.error("Failed to send error response to user.")

    @commands.slash_command(name="warn", description="Warns a user for a specified reason.")
    async def warn(
        self,
        ctx: discord.ApplicationContext,
        user: Option(discord.Member, "The user to warn.", required=True),  # type: ignore
        reason: Option(str, "Reason for the warning.", default="No reason provided."),  # type: ignore
        delete_message_seconds: Option(
            int,
            "Delete messages from (choose time range)",
            choices=DELETE_MESSAGE_CHOICES,
            default=0
        )  # type: ignore
    ) -> None:
        """Warn a user.

        The command defers the response, runs permission checks, and then
        delegates to the shared handler. Warnings do not remove the user
        from the guild but create an audit trail via the helper utilities.
        """
        await ctx.defer()
        
        if not await self.check_moderation_permissions(ctx, user, 'manage_messages'):
            return
            
        await self.handle_moderation_command(
            ctx, user, ActionType.WARN, reason, delete_message_seconds=delete_message_seconds
        )

    @commands.slash_command(name="timeout", description="Timeout a user for a specified duration.")
    async def timeout(
        self,
        ctx: discord.ApplicationContext,
        user: Option(discord.Member, "The user to timeout.", required=True),  # type: ignore
    duration: Option(str, "Duration of the timeout.", choices=DURATION_CHOICES, default="10 mins"),  # type: ignore
        reason: Option(str, "Reason for the timeout.", default="No reason provided."),  # type: ignore
        delete_message_seconds: Option(
            int,
            "Delete messages from (choose time range)",
            choices=DELETE_MESSAGE_CHOICES,
            default=0
        )  # type: ignore
    ) -> None:
        """Temporarily timeout a user.

        Duration strings are parsed via bot_helper.parse_duration_to_seconds.
        The command schedules the timeout and notifies the user; message
        deletion is optional and performed in the background.
        """
        await ctx.defer()
        
        if not await self.check_moderation_permissions(ctx, user, 'moderate_members'):
            return
            
        await self.handle_moderation_command(
            ctx, user, ActionType.TIMEOUT, reason, duration, delete_message_seconds
        )

    @commands.slash_command(name="kick", description="Kick a user from the server.")
    async def kick(
        self,
        ctx: discord.ApplicationContext,
        user: Option(discord.Member, "The user to kick.", required=True),  # type: ignore
        reason: Option(str, "Reason for the kick.", default="No reason provided."),  # type: ignore
        delete_message_seconds: Option(
            int,
            "Delete messages from (choose time range)",
            choices=DELETE_MESSAGE_CHOICES,
            default=0
        )  # type: ignore
    ) -> None:
        """Kick a member from the guild.

        Kicked users are removed from the server but can rejoin if they have
        an invite. The operation attempts to include the provided reason in
        audit logs and notifications.
        """
        await ctx.defer()
        
        if not await self.check_moderation_permissions(ctx, user, 'kick_members'):
            return
            
        await self.handle_moderation_command(
            ctx, user, ActionType.KICK, reason, delete_message_seconds=delete_message_seconds
        )

    @commands.slash_command(name="ban", description="Ban a user from the server.")
    async def ban(
        self,
        ctx: discord.ApplicationContext,
        user: Option(discord.Member, "The user to ban.", required=True),  # type: ignore
    duration: Option(str, "Duration of the ban.", choices=DURATION_CHOICES, default=PERMANENT_DURATION),  # type: ignore
        reason: Option(str, "Reason for the ban.", default="No reason provided."),  # type: ignore
        delete_message_seconds: Option(
            int,
            "Delete messages from (choose time range)",
            choices=DELETE_MESSAGE_CHOICES,
            default=0
        )  # type: ignore
    ) -> None:
        """Ban a member from the guild, optionally temporarily.

        If a non-permanent duration is provided, an unban is scheduled using
        the bot helper utilities. As with other commands, the operation
        notifies the target and records the reason for auditing.
        """
        await ctx.defer()
        
        if not await self.check_moderation_permissions(ctx, user, 'ban_members'):
            return
            
        await self.handle_moderation_command(
            ctx, user, ActionType.BAN, reason, duration, delete_message_seconds
        )


def setup(discord_bot_instance):
    """Cog setup entry point.

    This function is used by the bot loader to register the cog with the
    running bot instance.
    """
    discord_bot_instance.add_cog(ModerationActionCog(discord_bot_instance))