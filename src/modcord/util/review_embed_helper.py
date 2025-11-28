"""
Review embed builders for UI components.

This module provides standalone embed-building functions for the review system.
These functions are UI utilities and contain no business logic or database operations.

Key Functions:
- build_review_embed: Creates initial review request embed
- build_resolved_review_embed: Creates resolved version of review embed
- build_role_mentions: Formats moderator role mentions for Discord
"""

from __future__ import annotations
from uuid import UUID

import discord
from typing import List
from datetime import datetime, timezone
from modcord.datatypes.human_review_datatypes import HumanReviewData
from modcord.configuration.guild_settings import GuildSettings


def build_review_embed(
    review_items: List[HumanReviewData],
    batch_id: UUID,
) -> discord.Embed:
    """
    Build a consolidated embed containing all review items.
    
    Args:
        review_items: List of review items to include in the embed
        batch_id: Unique identifier for this review batch
    
    Returns:
        discord.Embed: Formatted embed with all review information
    """
    embed = discord.Embed(
        title="🛡️ AI Moderation Review Request",
        description=f"The AI flagged {len(review_items)} user(s) for human review.",
        color=discord.Color.gold(),
        timestamp=datetime.now(timezone.utc)
    )
    
    # Add each user as a field
    for idx, item in enumerate(review_items, 1):
        display_name = item.user.username or f"User {item.user.user_id}"
        mention = f"<@{item.user.user_id}>"

        user_info = f"**User:** {mention} (`{item.user.user_id}`)"
        
        # Add roles if present
        if item.user.roles:
            role_list = ", ".join(item.user.roles[:5])
            if len(item.user.roles) > 5:
                role_list += f" (+{len(item.user.roles) - 5} more)"
            user_info += f"\n**Roles:** {role_list}"
        
        # Add join date if available
        if item.user.join_date:
            user_info += f"\n**Joined:** {item.user.join_date}"
        
        user_info += f"\n**Reason:** {item.action.reason}"
        
        # Add message count
        message_count = len(item.user.messages)
        user_info += f"\n**Recent Messages:** {message_count} message{'s' if message_count != 1 else ''}"

        # Add past actions context
        if item.past_actions:
            past_actions_str = ", ".join(act.action.value for act in item.past_actions[:3])
            if len(item.past_actions) > 3:
                past_actions_str += f" (+{len(item.past_actions) - 3} more)"
            user_info += f"\n**History (7d):** {past_actions_str}"
        else:
            user_info += f"\n**History (7d):** No prior actions"

        embed.add_field(
            name=f"#{idx}: {display_name}",
            value=user_info,
            inline=False
        )
    
    # Add footer with batch ID
    embed.set_footer(text=f"ModCord | Batch: {str(batch_id)[:8]}")
    
    return embed


def build_resolved_review_embed(
    original_embed: discord.Embed,
    resolved_by_name: str
) -> discord.Embed:
    """
    Build a resolved embed from the original review embed.
    
    Args:
        original_embed: The original review request embed
        resolved_by_name: Name of the user who resolved the review
    
    Returns:
        discord.Embed: Updated embed showing resolved status
    """
    resolved_embed = discord.Embed(
        title="✅ Review Resolved",
        description=original_embed.description or "Review has been resolved.",
        color=discord.Color.green(),
        timestamp=original_embed.timestamp
    )
    
    # Copy fields from original embed
    for field in original_embed.fields:
        resolved_embed.add_field(
            name=field.name,
            value=field.value,
            inline=field.inline if field.inline is not None else False
        )
    
    # Update footer
    original_footer_text = original_embed.footer.text if original_embed.footer else "Review"
    resolved_embed.set_footer(
        text=f"{original_footer_text} | Resolved by {resolved_by_name}"
    )
    
    # Copy image if present
    if original_embed.image:
        resolved_embed.set_image(url=original_embed.image.url)
    
    return resolved_embed


def build_role_mentions(guild: discord.Guild, settings: GuildSettings) -> str | None:
    """
    Build mention string for moderator roles.
    
    Args:
        guild: Discord guild to get roles from
        settings: Guild settings containing moderator role IDs
    
    Returns:
        str | None: Mention string for all moderator roles, or None if no roles configured
    """
    if not settings.moderator_role_ids:
        return None
    
    mentions = []
    for role_id in settings.moderator_role_ids:
        role = guild.get_role(role_id)
        if role:
            mentions.append(role.mention)
    
    return " ".join(mentions) if mentions else None