"""
Moderation commands cog for the Discord Moderation Bot.
"""

import asyncio
import datetime
from typing import Optional

import discord
from discord import Option
from discord.ext import commands

from ..config.logger import get_logger
from ..models.action import ActionType
from ..services.moderation_service import ModerationService
from ..utils import constants
from ..utils import helpers

logger = get_logger(__name__)

class ModerationCog(commands.Cog):
    """
    Cog containing all moderation-related commands.
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.moderation_service = ModerationService(bot)
        logger.info("Moderation cog loaded")
    
    async def _check_moderation_permissions(
        self, 
        ctx: discord.ApplicationContext, 
        user: discord.Member,
        required_permission: str
    ) -> bool:
        """
        Common permission and validation checks for moderation commands.
        """
        if not helpers.has_permissions(ctx, **{required_permission: True}):
            await ctx.respond(f"You don't have permission to use this command.", ephemeral=True)
            return False
        
        if not isinstance(user, discord.Member):
            await ctx.followup.send("This user is not a member of the server.", ephemeral=True)
            return False
        
        if user.id == ctx.user.id:
            await ctx.followup.send("You cannot moderate yourself.", ephemeral=True)
            return False
        
        if user.guild_permissions.administrator:
            await ctx.followup.send("You cannot moderate an administrator.", ephemeral=True)
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
        """
        try:
            await self.moderation_service.send_dm_and_embed(ctx, user, action_type, reason, duration)
            
            if action_type == ActionType.TIMEOUT and duration:
                duration_seconds = helpers.parse_duration_to_seconds(duration)
                until = discord.utils.utcnow() + datetime.timedelta(seconds=duration_seconds)
                await user.timeout(until, reason=reason)
            elif action_type == ActionType.KICK:
                await user.kick(reason=reason)
            elif action_type == ActionType.BAN:
                await ctx.guild.ban(user, reason=reason)
                if duration and duration != constants.PERMANENT_DURATION:
                    duration_seconds = helpers.parse_duration_to_seconds(duration)
                    logger.info(f"Scheduling unban for {user.display_name} in {duration_seconds} seconds.")
                    asyncio.create_task(
                        self.moderation_service.unban_later(ctx.guild, user.id, ctx.channel, duration_seconds)
                    )
            
            if delete_message_seconds > 0:
                asyncio.create_task(
                    self.moderation_service.delete_messages_background(ctx, user, delete_message_seconds)
                )
                
        except Exception as e:
            await self.moderation_service.handle_error(ctx, e)

    @commands.slash_command(name="warn", description="Warn a user for a specified reason.")
    async def warn(
        self,
        ctx: discord.ApplicationContext,
        user: Option(discord.Member, "The user to warn.", required=True),
        reason: Option(str, "Reason for the warning.", default="No reason provided."),
        delete_message_seconds: Option(
            int,
            "Delete messages from (choose time range)",
            choices=constants.DELETE_MESSAGE_CHOICES,
            default=0
        )
    ) -> None:
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
        user: Option(discord.Member, "The user to timeout.", required=True),
        duration: Option(str, "Duration of the timeout.", choices=constants.DURATION_CHOICES, default="10 mins"),
        reason: Option(str, "Reason for the timeout.", default="No reason provided."),
        delete_message_seconds: Option(
            int,
            "Delete messages from (choose time range)",
            choices=constants.DELETE_MESSAGE_CHOICES,
            default=0
        )
    ) -> None:
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
        user: Option(discord.Member, "The user to kick.", required=True),
        reason: Option(str, "Reason for the kick.", default="No reason provided."),
        delete_message_seconds: Option(
            int,
            "Delete messages from (choose time range)",
            choices=constants.DELETE_MESSAGE_CHOICES,
            default=0
        )
    ) -> None:
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
        user: Option(discord.Member, "The user to ban.", required=True),
        duration: Option(str, "Duration of the ban.", choices=constants.DURATION_CHOICES, default=constants.PERMANENT_DURATION),
        reason: Option(str, "Reason for the ban.", default="No reason provided."),
        delete_message_seconds: Option(
            int,
            "Delete messages from (choose time range)",
            choices=constants.DELETE_MESSAGE_CHOICES,
            default=0
        )
    ) -> None:
        await ctx.defer()
        if not await self._check_moderation_permissions(ctx, user, 'ban_members'):
            return
        await self._handle_moderation_command(
            ctx, user, ActionType.BAN, reason, duration, delete_message_seconds
        )

def setup(bot):
    bot.add_cog(ModerationCog(bot))