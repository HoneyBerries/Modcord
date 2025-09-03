"""
Embed generation functions for the bot.
"""

import datetime
import discord

from ..models.action import ActionType
from .constants import PERMANENT_DURATION, DURATIONS

async def create_punishment_embed(
    action_type: ActionType,
    user: discord.User | discord.Member,
    reason: str,
    duration_str: str | None = None,
    issuer: discord.User | discord.Member | discord.ClientUser | None = None,
    bot_user: discord.ClientUser | None = None
) -> discord.Embed:
    """
    Build a standardized embed for logging moderation actions.
    """
    action_details = {
        ActionType.BAN:     {"color": discord.Color.red(),    "emoji": "🔨", "label": "Ban"},
        ActionType.KICK:    {"color": discord.Color.orange(), "emoji": "👢", "label": "Kick"},
        ActionType.WARN:    {"color": discord.Color.yellow(), "emoji": "⚠️", "label": "Warn"},
        ActionType.MUTE:    {"color": discord.Color.blue(),   "emoji": "🔇", "label": "Mute"},
        ActionType.TIMEOUT: {"color": discord.Color.blue(),   "emoji": "⏱️", "label": "Timeout"},
        ActionType.DELETE:  {"color": discord.Color.light_grey(), "emoji": "🗑️", "label": "Delete"},
        ActionType.NULL:    {"color": discord.Color.light_grey(), "emoji": "❓", "label": "No Action"},
    }

    unban_details = {"color": discord.Color.green(), "emoji": "🔓", "label": "Unban"}

    details = action_details.get(action_type, unban_details if str(action_type) == "unban" else action_details[ActionType.NULL])
    label = details.get("label", str(action_type).capitalize())

    embed = discord.Embed(
        title=f"{details['emoji']} {label} Issued",
        color=details['color'],
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    embed.add_field(name="User", value=f"{user.mention} (`{user.id}`)", inline=True)
    embed.add_field(name="Action", value=label, inline=True)
    if issuer:
        embed.add_field(name="Moderator", value=issuer.mention, inline=True)

    embed.add_field(name="Reason", value=reason, inline=False)

    if duration_str and duration_str != PERMANENT_DURATION:
        duration_seconds = DURATIONS.get(duration_str, 0)
        if duration_seconds > 0:
            expire_time = discord.utils.utcnow() + datetime.timedelta(seconds=duration_seconds)
            embed.add_field(
                name="Duration",
                value=f"{duration_str} (Expires: <t:{int(expire_time.timestamp())}:R>)",
                inline=False
            )
    elif duration_str:
        embed.add_field(name="Duration", value=duration_str, inline=False)

    if bot_user:
        embed.set_footer(text=f"Bot: {bot_user.name}")

    return embed
