"""
Embed creation utilities for moderation notifications.

This module provides utilities for creating Discord embeds for moderation actions.
"""

import datetime
import discord
from modcord.datatypes.action_datatypes import ActionType
from modcord.util.logger import get_logger
from modcord.util import discord_utils

logger = get_logger("moderation_embed")


async def create_punishment_embed(
    action_type: ActionType,
    user: discord.Member,
    guild: discord.Guild,
    reason: str,
    duration: datetime.timedelta | None = None
) -> discord.Embed:
    """
    Create an embed for a moderation action.
    
    Args:
        action_type: Type of moderation action
        user: Target user
        guild: Guild context
        reason: Reason for action
        duration: Optional duration timedelta (for timeout/ban)
    
    Returns:
        discord.Embed: Formatted embed
    """
    action_name = action_type.value.upper()
    embed = discord.Embed(
        title=f"{action_name} Notification",
        description=f"You have been {action_type.value}d in **{guild.name}**.",
        color=discord.Color.red()
    )
    embed.add_field(name="Reason", value=reason, inline=False)
    if duration:
        duration_str = discord_utils.format_duration(int(duration.total_seconds()))
        embed.add_field(name="Duration", value=duration_str, inline=False)
    return embed