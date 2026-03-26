"""
Embed creation utilities for moderation notifications.

This module provides utilities for creating Discord embeds for moderation actions,
using ActionData as the canonical input.

No interactive components — no persistence changes needed.

Changes from v1:
  - User avatar set as embed thumbnail for quick visual identification.
  - Inline field layout groups related info side-by-side.
  - User ID shown below the mention for audit trail convenience.
  - Duration field only rendered when meaningful (> 0 seconds).
  - Color palette unchanged; emoji mapping unchanged.
"""

import datetime

import discord

from modcord.datatypes.action_datatypes import ActionData, ActionType
from modcord.util.discord import discord_utils
from modcord.util.logger import get_logger

logger = get_logger("ACTION EMBED UI")


# ──────────────────────────────────────────────────────────────
# Mappings
# ──────────────────────────────────────────────────────────────

ACTION_EMOJIS = {
    ActionType.WARN: "⚠️",
    ActionType.DELETE: "🗑️",
    ActionType.TIMEOUT: "⏱️",
    ActionType.KICK: "👢",
    ActionType.BAN: "🔨",
}

ACTION_COLORS = {
    ActionType.WARN: discord.Color.gold(),
    ActionType.DELETE: discord.Color.orange(),
    ActionType.TIMEOUT: discord.Color.orange(),
    ActionType.KICK: discord.Color.red(),
    ActionType.BAN: discord.Color.dark_red(),
}


# ──────────────────────────────────────────────────────────────
# Builder
# ──────────────────────────────────────────────────────────────

async def create_action_embed(
    action: ActionData,
    user: discord.Member,
    guild: discord.Guild,
    admin: discord.User | discord.ClientUser | discord.Member,
    duration: datetime.timedelta | None = None,
) -> discord.Embed:
    """
    Create an embed for a moderation action using ActionData.

    Args:
        action:   ActionData containing action type, reason, and other details.
        user:     Target user (Member in the guild).
        guild:    Guild context.
        admin:    Admin or bot user responsible for the action.
        duration: Optional timedelta for timed actions (timeout / temp-ban).
                  Computed from action fields if not provided.

    Returns:
        discord.Embed formatted with action details, inline field layout,
        user avatar thumbnail, and (where relevant) duration + expiry.
    """
    emoji = ACTION_EMOJIS.get(action.action, "⚙️")
    color = ACTION_COLORS.get(action.action, discord.Color.red())
    action_name = action.action.value.capitalize()

    embed = discord.Embed(
        title=f"{emoji}  {action_name} Issued",
        color=color,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )

    # User avatar as thumbnail — makes the offender immediately recognisable
    # in a busy Audit Log feed.
    avatar_url = user.display_avatar.url
    embed.set_thumbnail(url=avatar_url)

    # ── User row ──────────────────────────────────────────────
    embed.add_field(name="User", value=user.mention, inline=True)

    # ── Admin row ─────────────────────────────────────────────
    embed.add_field(name="Moderator", value=admin.mention, inline=True)

    # ── Reason (full width) ───────────────────────────────────
    embed.add_field(name="Reason", value=action.reason, inline=False)

    # ── Duration + expiry (timed actions only) ────────────────
    if duration and duration.total_seconds() > 0:
        duration_str = discord_utils.format_duration(int(duration.total_seconds()))

        now = datetime.datetime.now(datetime.timezone.utc)
        expires_at = now + duration
        expires_unix = int(expires_at.timestamp())

        embed.add_field(
            name="Duration",
            value=f"{duration_str}  ·  Expires <t:{expires_unix}:R>",
            inline=False,
        )

    embed.set_footer(text=guild.name)

    return embed