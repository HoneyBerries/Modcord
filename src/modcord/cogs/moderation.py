"""
Moderation commands cog for the Discord Moderation Bot.
"""

import asyncio
import datetime
from typing import Optional

import discord
from discord import Option
from discord.ext import commands

from ..logger import get_logger
from ..actions import ActionType
from .. import bot_helper

logger = get_logger("moderation_cog")


class ModerationCog(commands.Cog):
    """
    Cog containing all moderation-related commands.
    """
    
    def __init__(self, discord_bot_instance):
        self.discord_bot_instance = discord_bot_instance
        logger.info("Moderation cog loaded")
    
    async def _check_moderation_permissions(
        self, 
        application_context: discord.ApplicationContext, 
        target_user: discord.Member,
        required_permission_name: str
    ) -> bool:
        """
        Common permission and validation checks for moderation commands.
        
        Args:
            application_context: The command context
            target_user: The target user
            required_permission_name: The required permission (e.g., 'manage_messages')
            
        Returns:
            True if checks pass, False otherwise
        """
        # Check bot permissions
        if not bot_helper.has_permissions(application_context, **{required_permission_name: True}):
            await application_context.respond(f"You don't have permission to use this command.", ephemeral=True)
            return False
        
        # Check if target is a member
        if not isinstance(user, discord.Member):
            await ctx.followup.send("This user is not a member of the server.", ephemeral=True)
            return False
        
        # Check if user is trying to moderate themselves
        if user.id == ctx.user.id:
            await ctx.followup.send("Don't do self harm.", ephemeral=True)
            return False
        
        # Check if target is an administrator
        if user.guild_permissions.administrator:
            await ctx.followup.send("You cannot bully admins.", ephemeral=True)
            return False
        
        return True
    
    async def _handle_moderation_command(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Member,
        action_type: ActionType,
        reason: str,
        duration: Optional[str] = None,
        delete_message_seconds: int = 0
    ) -> None:
        """
        Common handler for moderation commands.
        
        Args:
            ctx: The command context
            user: The target user
            action_type: The type of moderation action
            reason: Reason for the action
            duration: Duration for timed actions (optional)
            delete_message_seconds: Seconds of messages to delete
        """
        try:
            # Send DM and embed first
            await bot_helper.send_dm_and_embed(ctx, user, action_type, reason, duration)
            
            # Perform the specific action
            if action_type == ActionType.TIMEOUT and duration:
                duration_seconds = bot_helper.parse_duration_to_seconds(duration)
                until = discord.utils.utcnow() + datetime.timedelta(seconds=duration_seconds)
                await user.timeout(until, reason=reason)
            elif action_type == ActionType.KICK:
                await user.kick(reason=reason)
            elif action_type == ActionType.BAN:
                await ctx.guild.ban(user, reason=reason)
                if duration and duration != bot_helper.PERMANENT_DURATION:
                    duration_seconds = bot_helper.parse_duration_to_seconds(duration)
                    logger.info(f"Scheduling unban for {user.display_name} in {duration_seconds} seconds.")
                    asyncio.create_task(
                        bot_helper.unban_later(ctx.guild, user.id, ctx.channel, duration_seconds, self.bot)
                    )
            
            # Delete messages in background if requested
            if delete_message_seconds > 0:
                asyncio.create_task(
                    bot_helper.delete_messages_background(ctx, user, delete_message_seconds)
                )
                
        except Exception as e:
            await bot_helper.handle_error(ctx, e)

    @commands.slash_command(name="warn", description="Warn a user for a specified reason.")
    async def warn(
        self,
        ctx: discord.ApplicationContext,
        user: Option(discord.Member, "The user to warn.", required=True),  # type: ignore
        reason: Option(str, "Reason for the warning.", default="No reason provided."),  # type: ignore
        delete_message_seconds: Option(
            int,
            "Delete messages from (choose time range)",
            choices=bot_helper.DELETE_MESSAGE_CHOICES,
            default=0
        )  # type: ignore
    ) -> None:
        """Warn a user for a specified reason."""
        await ctx.defer()
        
        if not await self._check_moderation_permissions(ctx, user, 'manage_messages'):
            return
            
        await self._handle_moderation_command(
            ctx, user, ActionType.WARN, reason, delete_message_seconds=delete_message_seconds
        )

    @commands.slash_command(name="timeout", description="Timeout a user for a specified duration.")
    async def timeout(
        self,
        ctx: discord.ApplicationContext,
        user: Option(discord.Member, "The user to timeout.", required=True),  # type: ignore
        duration: Option(str, "Duration of the timeout.", choices=bot_helper.DURATION_CHOICES, default="10 mins"),  # type: ignore
        reason: Option(str, "Reason for the timeout.", default="No reason provided."),  # type: ignore
        delete_message_seconds: Option(
            int,
            "Delete messages from (choose time range)",
            choices=bot_helper.DELETE_MESSAGE_CHOICES,
            default=0
        )  # type: ignore
    ) -> None:
        """Timeout a user for a specified duration."""
        await ctx.defer()
        
        if not await self._check_moderation_permissions(ctx, user, 'moderate_members'):
            return
            
        await self._handle_moderation_command(
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
            choices=bot_helper.DELETE_MESSAGE_CHOICES,
            default=0
        )  # type: ignore
    ) -> None:
        """Kick a user from the server."""
        await ctx.defer()
        
        if not await self._check_moderation_permissions(ctx, user, 'kick_members'):
            return
            
        await self._handle_moderation_command(
            ctx, user, ActionType.KICK, reason, delete_message_seconds=delete_message_seconds
        )

    @commands.slash_command(name="ban", description="Ban a user from the server.")
    async def ban(
        self,
        ctx: discord.ApplicationContext,
        user: Option(discord.Member, "The user to ban.", required=True),  # type: ignore
        duration: Option(str, "Duration of the ban.", choices=bot_helper.DURATION_CHOICES, default=bot_helper.PERMANENT_DURATION),  # type: ignore
        reason: Option(str, "Reason for the ban.", default="No reason provided."),  # type: ignore
        delete_message_seconds: Option(
            int,
            "Delete messages from (choose time range)",
            choices=bot_helper.DELETE_MESSAGE_CHOICES,
            default=0
        )  # type: ignore
    ) -> None:
        """Ban a user from the server."""
        await ctx.defer()
        
        if not await self._check_moderation_permissions(ctx, user, 'ban_members'):
            return
            
        await self._handle_moderation_command(
            ctx, user, ActionType.BAN, reason, duration, delete_message_seconds
        )


def setup(discord_bot_instance):
    """Setup function for the cog."""
    discord_bot_instance.add_cog(ModerationCog(discord_bot_instance))