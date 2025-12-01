"""
Command action classes for manual moderation commands.

This module defines command action classes that extend ActionData for direct execution
of moderation actions through Discord slash commands. All execution logic is delegated
to moderation_helper.apply_action to avoid duplication.
"""

from __future__ import annotations

import discord

from modcord.datatypes.action_datatypes import ActionData, ActionType
from modcord.datatypes.discord_datatypes import UserID, GuildID, ChannelID
from modcord.moderation import moderation_helper
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
        bot: discord.Bot,
    ) -> bool:
        """Execute the moderation action.
        
        Populates the ActionData fields from context and delegates to apply_action.

        Args:
            ctx: Slash command context.
            user: Guild member to apply the action to.
            bot: Discord bot instance.
            
        Returns:
            bool: True if action was successfully applied.
        """
        # Populate ActionData fields from context
        self.guild_id = GuildID.from_guild(ctx.guild)
        self.channel_id = ChannelID.from_channel(ctx.channel)
        self.user_id = UserID.from_user(user)
        
        # Get channel for notifications
        channel = ctx.channel
        if not isinstance(channel, discord.TextChannel):
            logger.warning("Command executed in non-text channel, trying to find suitable channel")
            channel = ctx.guild.system_channel or next(
                (c for c in ctx.guild.text_channels if c.permissions_for(ctx.guild.me).send_messages),
                None
            )
        
        if channel is None:
            logger.error("No suitable channel found for action notification")
            return False
        
        # Delegate to the unified apply_action function
        return await moderation_helper.apply_action(
            action=self,
            member=user,
            bot=bot)


class WarnCommand(CommandAction):
    """Warn action for manual commands."""

    def __init__(self, reason: str = "No reason provided."):
        """Initialize a warn action."""
        super().__init__(
            guild_id=GuildID(0),
            channel_id=ChannelID(0),
            user_id=UserID(0),
            action=ActionType.WARN,
            reason=reason,
        )


class TimeoutCommand(CommandAction):
    """Timeout action for manual commands."""

    def __init__(self, reason: str = "No reason provided.", duration_minutes: int = 10):
        """Initialize a timeout action."""
        super().__init__(
            guild_id=GuildID(0),
            channel_id=ChannelID(0),
            user_id=UserID(0),
            action=ActionType.TIMEOUT,
            reason=reason,
            timeout_duration=duration_minutes,
        )


class KickCommand(CommandAction):
    """Kick action for manual commands."""

    def __init__(self, reason: str = "No reason provided."):
        """Initialize a kick action."""
        super().__init__(
            guild_id=GuildID(0),
            channel_id=ChannelID(0),
            user_id=UserID(0),
            action=ActionType.KICK,
            reason=reason,
        )


class BanCommand(CommandAction):
    """Ban action for manual commands."""

    def __init__(self, duration_minutes: int = 0, reason: str = "No reason provided."):
        """Initialize a ban action.
        
        Args:
            duration_minutes: Ban duration in minutes. 0 or negative = permanent.
            reason: Reason for the ban.
        """
        super().__init__(
            guild_id=GuildID(0),
            channel_id=ChannelID(0),
            user_id=UserID(0),
            action=ActionType.BAN,
            reason=reason,
            ban_duration=duration_minutes,
        )
