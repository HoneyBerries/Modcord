"""
Command action classes for manual moderation commands.

This module defines command action classes that extend ActionData for direct execution
of moderation actions through Discord slash commands.
"""

from __future__ import annotations

import datetime
import discord

from modcord.datatypes.action_datatypes import ActionData, ActionType
from modcord.datatypes.discord_datatypes import UserID, GuildID
from modcord.scheduler.unban_scheduler import UNBAN_SCHEDULER
from modcord.moderation.moderation_helper import execute_moderation_notification
from modcord.database.database import get_db
from modcord.util.logger import get_logger

logger = get_logger("command_datatypes")


class CommandAction(ActionData):
    """Base class for manual moderation command actions.
    
    Extends ActionData with an execute method for direct execution
    without requiring a Discord message pivot.
    """

    async def execute(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Member,
        bot_instance: discord.Bot,
    ) -> None:
        """Execute the moderation action.

        Args:
            ctx: Slash command context.
            user: Guild member to apply the action to.
            bot_instance: Discord bot instance for scheduling tasks.
        """
        raise NotImplementedError("Subclasses must implement execute()")


class WarnCommand(CommandAction):
    """Warn action for manual commands."""

    def __init__(self, reason: str = "No reason provided."):
        """Initialize a warn action."""
        super().__init__(
            guild_id=GuildID(0),  # Will be set by caller
            user_id=UserID(0),  # Will be set by caller
            action=ActionType.WARN,
            reason=reason,
        )

    async def execute(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Member,
        bot_instance: discord.Bot,
    ) -> None:
        """Execute warn action by creating embed and DM."""
        self.guild_id = GuildID.from_guild(ctx.guild)
        self.user_id = UserID.from_user(user)

        try:
            await execute_moderation_notification(
                action_type=ActionType.WARN,
                user=user,
                guild=ctx.guild,
                reason=self.reason,
                channel=ctx.channel,
            )
            await get_db().log_moderation_action(self)
        except Exception as exc:
            logger.error("[COMMAND DATATYPES] Failed to process warn for user %s: %s", self.user_id, exc)


class TimeoutCommand(CommandAction):
    """Timeout action for manual commands."""

    def __init__(self, reason: str = "No reason provided.", duration_minutes: int = 10):
        """Initialize a timeout action."""
        super().__init__(
            guild_id=GuildID(0),
            user_id=UserID(0),
            action=ActionType.TIMEOUT,
            reason=reason,
            timeout_duration=duration_minutes,
        )

    async def execute(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Member,
        bot_instance: discord.Bot,
    ) -> None:
        """Execute timeout action."""
        self.guild_id = GuildID.from_guild(ctx.guild)
        self.user_id = UserID.from_user(user)
        
        duration_minutes = self.timeout_duration or 10
        # Handle -1 (permanent) by capping to Discord's 28-day max
        if duration_minutes == -1:
            duration_minutes = 28 * 24 * 60
        
        duration_seconds = duration_minutes * 60
        until = discord.utils.utcnow() + datetime.timedelta(seconds=duration_seconds)

        try:
            await user.timeout(until, reason=f"Manual Mod: {self.reason}")
            await execute_moderation_notification(
                action_type=ActionType.TIMEOUT,
                user=user,
                guild=ctx.guild,
                reason=self.reason,
                channel=ctx.channel,
                duration=datetime.timedelta(seconds=duration_seconds),
            )
            await get_db().log_moderation_action(self)
        except Exception as exc:
            logger.error("[COMMAND DATATYPES] Failed to timeout user %s: %s", self.user_id, exc)
            raise


class KickCommand(CommandAction):
    """Kick action for manual commands."""

    def __init__(self, reason: str = "No reason provided."):
        """Initialize a kick action."""
        super().__init__(
            guild_id=GuildID(0),
            user_id=UserID(0),
            action=ActionType.KICK,
            reason=reason,
        )

    async def execute(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Member,
        bot_instance: discord.Bot,
    ) -> None:
        """Execute kick action."""
        self.guild_id = GuildID.from_guild(ctx.guild)
        self.user_id = UserID.from_user(user)

        try:
            await ctx.guild.kick(user, reason=f"Manual Mod: {self.reason}")
            await execute_moderation_notification(
                action_type=ActionType.KICK,
                user=user,
                guild=ctx.guild,
                reason=self.reason,
                channel=ctx.channel,
            )
            await get_db().log_moderation_action(self)
        except Exception as exc:
            logger.error("[COMMAND DATATYPES] Failed to kick user %s: %s", self.user_id, exc)
            raise


class BanCommand(CommandAction):
    """Ban action for manual commands."""

    def __init__(self, duration_minutes: int, reason: str = "No reason provided."):
        """Initialize a ban action."""
        super().__init__(
            guild_id=GuildID(0),
            user_id=UserID(0),
            action=ActionType.BAN,
            reason=reason,
            ban_duration=duration_minutes,
        )

    async def execute(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Member,
        bot_instance: discord.Bot,
    ) -> None:
        """Execute ban action."""
        self.guild_id = GuildID.from_guild(ctx.guild)
        self.user_id = UserID.from_user(user)
        
        duration_minutes = self.ban_duration or 0
        is_permanent = duration_minutes <= 0
        duration_seconds = 0 if is_permanent else duration_minutes * 60

        try:
            await ctx.guild.ban(user, reason=f"Manual Mod: {self.reason}")
            duration = datetime.timedelta(seconds=duration_seconds) if duration_seconds > 0 else None
            await execute_moderation_notification(
                action_type=ActionType.BAN,
                user=user,
                guild=ctx.guild,
                reason=self.reason,
                channel=ctx.channel,
                duration=duration,
            )
            await get_db().log_moderation_action(self)
            
            # Schedule unban if not permanent
            if not is_permanent:
                try:
                    await UNBAN_SCHEDULER.schedule(
                        guild=ctx.guild,
                        user_id=self.user_id,
                        channel=ctx.channel if isinstance(ctx.channel, (discord.TextChannel, discord.Thread)) else None,
                        duration_seconds=duration_seconds,
                        bot=bot_instance,
                        reason="Ban duration expired.",
                    )
                except Exception as exc:
                    logger.error("[COMMAND DATATYPES] Failed to schedule unban for user %s: %s", self.user_id, exc)
        except Exception as exc:
            logger.error("[COMMAND DATATYPES] Failed to ban user %s: %s", self.user_id, exc)
            raise