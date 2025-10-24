"""
Moderation cog: commands for taking disciplinary actions on server members.

This module provides a collection of slash commands that a moderator can use
to warn, timeout, kick, or ban users. Commands use CommandAction subclasses
from moderation_datatypes that extend ActionData and provide execute methods.

Design notes and expectations
- Commands perform standard safety checks (permission, guild member,
  self-moderation prevention, administrator protection).
- CommandAction subclasses encapsulate execution logic and DM/embed handling.
- All command actions follow the same pattern as ActionData but with
  direct execution capability.
- Errors are caught and reported to the invoker via ephemeral responses.

Quick usage example
    # In your bot setup code
    from modcord.bot.cogs.moderation_cmds import ModerationActionCog
    bot.add_cog(ModerationActionCog(bot))

Permissions
- Each command checks for the appropriate moderator permission before
  executing. If the permission check fails the command replies
  ephemerally to the invoking user.
"""

import asyncio
import discord
from discord import Option
from discord.ext import commands

from modcord.util.discord_utils import (
    has_permissions,
    PERMANENT_DURATION,
    DURATION_CHOICES,
    DELETE_MESSAGE_CHOICES,
    parse_duration_to_minutes,
    delete_messages_background,
)
from modcord.moderation.moderation_datatypes import (
    CommandAction,
    WarnCommand,
    TimeoutCommand,
    KickCommand,
    BanCommand,
)
from modcord.util.logger import get_logger

logger = get_logger("moderation_cog")


class ModerationActionCog(commands.Cog):
    """Cog containing moderation-related slash commands.

    Each command defers its response, performs permission and validation checks,
    creates a CommandAction instance, and executes it. CommandAction subclasses
    handle all Discord API interactions.

    The bot instance passed into the cog is used for executing actions and
    scheduling tasks.
    """

    def __init__(self, discord_bot_instance):
        """Store the bot instance for executing actions.

        Parameters
        ----------
        discord_bot_instance:
            Active :class:`discord.Bot` instance used for moderation and scheduling tasks.
        """
        self.discord_bot_instance = discord_bot_instance
        logger.info("Moderation cog loaded")

    async def check_moderation_permissions(
        self,
        application_context: discord.ApplicationContext,
        target_user: discord.Member,
        required_permission_name: str,
    ) -> bool:
        """Run shared pre-checks for moderation commands.

        Parameters
        ----------
        application_context:
            Slash command context for the invoking moderator.
        target_user:
            Guild member the moderation action targets.
        required_permission_name:
            Permission attribute name required for the action.

        Returns
        -------
        bool
            ``True`` when allowed to proceed; ``False`` if an error was sent to invoker.
        """
        # Check invoking user's permission
        if not has_permissions(application_context, **{required_permission_name: True}):
            await application_context.defer(ephemeral=True)
            await application_context.send_followup(
                "You do not have permission to use this command."
            )
            return False

        # Check if target is a member of this server
        if not isinstance(target_user, discord.Member):
            await application_context.defer(ephemeral=True)
            await application_context.send_followup(
                "The specified user is not a member of this server."
            )
            return False

        # Prevent self-moderation
        if target_user.id == application_context.user.id:
            await application_context.defer(ephemeral=True)
            await application_context.send_followup(
                "You cannot perform moderation actions on yourself."
            )
            return False

        # Protect administrators from moderation via these commands
        if target_user.guild_permissions.administrator:
            await application_context.defer(ephemeral=True)
            await application_context.send_followup(
                "You cannot perform moderation actions against administrators."
            )
            return False

        return True

    async def execute_command_action(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Member,
        action: CommandAction,
        delete_message_minutes: int = 0,
    ) -> None:
        """Execute a command action and handle errors.

        Parameters
        ----------
        ctx:
            Slash command context.
        user:
            Guild member the action applies to.
        action:
            CommandAction instance to execute.
        delete_message_minutes:
            Optional message deletion window, in minutes.
        """
        try:
            await action.execute(ctx, user, self.discord_bot_instance)

            # Delete messages in background if requested
            if delete_message_minutes > 0:
                asyncio.create_task(delete_messages_background(ctx, user, delete_message_minutes))

        except Exception as e:
            logger.exception("Error executing moderation action: %s", e)
            try:
                await ctx.defer(ephemeral=True)
                await ctx.send_followup(
                    "An error occurred while processing the command."
                )
            except Exception:
                logger.error("Failed to send error response to user.")

    @commands.slash_command(name="warn", description="Warns a user for a specified reason.")
    async def warn(
        self,
        ctx: discord.ApplicationContext,
        user: Option(discord.Member, "The user to warn.", required=True),  # type: ignore
        reason: Option(str, "Reason for the warning.", default="No reason provided."),  # type: ignore
        delete_message_minutes: Option(
            int,
            "Delete messages from (choose time range, in minutes)",
            choices=DELETE_MESSAGE_CHOICES,
            default=0,
        ),  # type: ignore
    ) -> None:
        """Warn a user.

        Warnings do not remove the user from the guild but create an audit
        trail via embeds and optional message deletion.
        """
        await ctx.defer(ephemeral=True)

        if not await self.check_moderation_permissions(ctx, user, "manage_messages"):
            await ctx.send_followup("You lack the required permissions to warn this user.")
            return

        action = WarnCommand(reason=reason)
        await self.execute_command_action(
            ctx, user, action, delete_message_minutes=delete_message_minutes
        )

    @commands.slash_command(name="timeout", description="Timeout a user for a specified duration.")
    async def timeout(
        self,
        ctx: discord.ApplicationContext,
        user: Option(discord.Member, "The user to timeout.", required=True),  # type: ignore
        duration: Option(
            str, "Duration of the timeout.", choices=DURATION_CHOICES, default="10 mins"
        ),  # type: ignore
        reason: Option(str, "Reason for the timeout.", default="No reason provided."),  # type: ignore
        delete_message_minutes: Option(
            int,
            "Delete messages from (choose time range, in minutes)",
            choices=DELETE_MESSAGE_CHOICES,
            default=0,
        ),  # type: ignore
    ) -> None:
        """Temporarily timeout a user.

        The user cannot send messages, reactions, or join voice channels
        for the specified duration.
        """
        await ctx.defer(ephemeral=True)

        if not await self.check_moderation_permissions(ctx, user, "moderate_members"):
            await ctx.send_followup("You lack the required permissions to timeout this user.")
            return

        timeout_minutes = parse_duration_to_minutes(duration)
        action = TimeoutCommand(reason=reason, duration_minutes=timeout_minutes)
        await self.execute_command_action(
            ctx, user, action, delete_message_minutes=delete_message_minutes
        )

    @commands.slash_command(name="kick", description="Kick a user from the server.")
    async def kick(
        self,
        ctx: discord.ApplicationContext,
        user: Option(discord.Member, "The user to kick.", required=True),  # type: ignore
        reason: Option(str, "Reason for the kick.", default="No reason provided."),  # type: ignore
        delete_message_minutes: Option(
            int,
            "Delete messages from (choose time range, in minutes)",
            choices=DELETE_MESSAGE_CHOICES,
            default=0,
        ),  # type: ignore
    ) -> None:
        """Kick a member from the guild.

        Kicked users are removed from the server but can rejoin if they have
        an invite.
        """
        await ctx.defer(ephemeral=True)

        if not await self.check_moderation_permissions(ctx, user, "kick_members"):
            await ctx.send_followup("You lack the required permissions to kick this user.")
            return

        action = KickCommand(reason=reason)
        await self.execute_command_action(
            ctx, user, action, delete_message_minutes=delete_message_minutes
        )

    @commands.slash_command(name="ban", description="Ban a user from the server.")
    async def ban(
        self,
        ctx: discord.ApplicationContext,
        user: Option(discord.Member, "The user to ban.", required=True),  # type: ignore
        duration: Option(
            str,
            "Duration of the ban.",
            choices=DURATION_CHOICES,
            default=PERMANENT_DURATION,
        ),  # type: ignore
        reason: Option(str, "Reason for the ban.", default="No reason provided."),  # type: ignore
        delete_message_minutes: Option(
            int,
            "Delete messages from (choose time range, in minutes)",
            choices=DELETE_MESSAGE_CHOICES,
            default=0,
        ),  # type: ignore
    ) -> None:
        """Ban a user from the guild.

        Banned users are removed from the server and cannot rejoin unless
        unbanned.
        """
        await ctx.defer(ephemeral=True)

        if not await self.check_moderation_permissions(ctx, user, "ban_members"):
            await ctx.send_followup("You lack the required permissions to ban this user.")
            return

        ban_minutes = parse_duration_to_minutes(duration) if duration != PERMANENT_DURATION else None
        action = BanCommand(reason=reason, duration_minutes=ban_minutes)
        await self.execute_command_action(
            ctx, user, action, delete_message_minutes=delete_message_minutes
        )


def setup(discord_bot_instance):
    """Cog setup entry point.

    This function is used by the bot loader to register the cog with the
    running bot instance.
    """
    discord_bot_instance.add_cog(ModerationActionCog(discord_bot_instance))