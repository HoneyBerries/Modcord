"""
Embed creation utilities for moderation notifications.

This module provides utilities for creating Discord embeds for moderation actions.
"""

import datetime
import discord
from modcord.datatypes.action_datatypes import ActionType
from modcord.util.logger import get_logger
from modcord.util import discord_utils

logger = get_logger("action_embed")


# Emoji mapping for action types
ACTION_EMOJIS = {
    ActionType.WARN: "⚠️",
    ActionType.DELETE: "🗑️",
    ActionType.TIMEOUT: "⏱️",
    ActionType.KICK: "👢",
    ActionType.BAN: "🔨",
    ActionType.REVIEW: "🔍",
}

# Color mapping for action types
ACTION_COLORS = {
    ActionType.WARN: discord.Color.gold(),
    ActionType.DELETE: discord.Color.orange(),
    ActionType.TIMEOUT: discord.Color.orange(),
    ActionType.KICK: discord.Color.red(),
    ActionType.BAN: discord.Color.dark_red(),
    ActionType.REVIEW: discord.Color.blue(),
}


async def create_punishment_embed(
    action_type: ActionType,
    user: discord.Member,
    guild: discord.Guild,
    reason: str,
    admin: discord.User | discord.ClientUser | discord.Member,
    duration: datetime.timedelta | None,
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
        discord.Embed: Formatted embed with action details, duration, and expiry time
    """
    emoji = ACTION_EMOJIS.get(action_type, "⚙️")
    color = ACTION_COLORS.get(action_type, discord.Color.red())
    action_name = action_type.value.capitalize()
    
    embed = discord.Embed(
        title=f"{emoji} {action_name} Issued",
        color=color,
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    
    # User field with mention and ID
    embed.add_field(
        name="User Punished",
        value=f"{user.mention}",
        inline=True
    )
    
    # Reason field
    embed.add_field(name="Reason", value=reason, inline=False)
    
    # Duration and expiry for timeout/ban actions
    if duration and duration.total_seconds() > 0:
        duration_str = discord_utils.format_duration(int(duration.total_seconds()))
        
        # Calculate expiry timestamp
        now = datetime.datetime.now(datetime.timezone.utc)
        expires_at = now + duration
        expires_unix = int(expires_at.timestamp())
        
        # Format: "30 mins (Expires: <relative timestamp>)"
        duration_with_expiry = f"{duration_str} (Expires: <t:{expires_unix}:R>)"
        
        embed.add_field(name="Duration", value=duration_with_expiry, inline=False)
    
    embed.add_field(name="Admin", value=admin.mention, inline=True)
    
    # Add guild name in the footer
    embed.set_footer(text=f"Guild: {guild.name}")
    
    return embed