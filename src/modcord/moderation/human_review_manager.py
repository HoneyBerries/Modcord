"""
Human moderator review notification system.

This module manages the creation and tracking of review requests that require
human moderator intervention. It consolidates multiple review actions per batch
into a single embed to prevent spam and provides persistent tracking of review status.

Key Features:
- Batch consolidation: Groups all review actions per batch into one embed per guild
- Persistent tracking: Stores review requests in database with status tracking
- Interactive UI: Integrates with HumanReviewResolutionView for button interactions
- User context: Includes past moderation history in review embeds
"""

from __future__ import annotations

import discord
from typing import List
from dataclasses import dataclass
import uuid

from modcord.util.logger import get_logger
from modcord.moderation.moderation_datatypes import (
    ActionData,
    ModerationUser,
    format_past_actions,
)
from modcord.bot.review_ui import HumanReviewResolutionView
from modcord.util.review_embeds import build_review_embed, build_role_mentions
from modcord.configuration.guild_settings import GuildSettings

logger = get_logger("human_review_manager")


@dataclass
class HumanReviewData:
    """User-centric review item for human moderator review.
    
    Represents a single user flagged for review with their complete context.
    Admins review the user's overall behavior pattern rather than individual messages.
    """

    action: ActionData
    user: ModerationUser
    past_actions: List[dict]


class HumanReviewManager:
    """
    Manages human moderator review notifications and tracking.
    
    This class consolidates review actions from a batch into a single embed per guild,
    sends them to configured review channels, and tracks their status in the database.
    """
    
    def __init__(self, bot: discord.Bot):
        """
        Initialize the review notification manager.
        
        Args:
            bot: Discord bot instance for accessing guilds and channels
        """
        self.bot = bot
        self._active_batches: dict[int, dict[str, HumanReviewData]] = {}  # guild_id -> {user_id -> HumanReviewData}
    
    async def add_item_for_review(
        self,
        guild: discord.Guild,
        user: ModerationUser,
        action: ActionData
    ) -> None:
        """
        Add a user-centric review item to the current batch for this guild.
        
        Items are accumulated per guild and will be sent together when send_review_embed is called.
        Focuses on the user's overall behavior rather than individual messages.
        
        Args:
            guild: Discord guild where the review is needed
            user: ModerationUser containing complete user context and all their messages
            action: ActionData containing the review reason
        """
        if guild.id not in self._active_batches:
            self._active_batches[guild.id] = {}
        
        # Deduplicate by user_id - only add if not already present
        if user.user_id in self._active_batches[guild.id]:
            logger.debug(
                "[REVIEW] User %s already in review batch for guild %s, skipping duplicate",
                user.user_id,
                guild.id,
            )
            return

        review_item = HumanReviewData(
            action=action,
            user=user,
            past_actions=format_past_actions(user.past_actions),
        )
        
        self._active_batches[guild.id][user.user_id] = review_item
        logger.debug(
            "[REVIEW] Added review item for user %s in guild %s (reason: %s)",
            user.user_id,
            guild.id,
            action.reason,
        )
    
    async def send_review_embed(self, guild: discord.Guild, settings: GuildSettings) -> bool:
        """
        Finalize and send the consolidated review embed for this guild's batch.
        
        Creates a single embed containing all review items for this batch,
        sends it to all configured review channels.
        
        Args:
            guild: Discord guild to finalize reviews for
            settings: Guild settings containing review channel configuration
        
        Returns:
            bool: True if review was successfully sent, False otherwise
        """
        if guild.id not in self._active_batches or not self._active_batches[guild.id]:
            logger.debug("[REVIEW] No review items to finalize for guild %s", guild.id)
            return False
        
        # Convert dict values to list for embed builder
        review_items = list(self._active_batches[guild.id].values())
        batch_id = str(uuid.uuid4())
        
        # Build consolidated embed using utility function
        embed = build_review_embed(review_items, batch_id, self.bot.user)
        
        # Send to all review channels
        sent_messages = []
        
        for channel_id in settings.review_channel_ids:
            review_channel = guild.get_channel(channel_id)
            if review_channel and isinstance(review_channel, (discord.TextChannel, discord.Thread)):
                try:
                    view = HumanReviewResolutionView(batch_id=batch_id, guild_id=guild.id, bot=self.bot)
                    mention_content = build_role_mentions(guild, settings)
                    
                    sent_message = await review_channel.send(
                        content=mention_content,
                        embed=embed,
                        view=view
                    )
                    sent_messages.append((channel_id, sent_message.id))
                    logger.info("[REVIEW] Sent review batch %s to channel %s", batch_id, channel_id)
                except Exception as e:
                    logger.error("[REVIEW] Failed to send review to channel %s: %s", channel_id, e)
        
        if sent_messages:
            logger.info("[REVIEW] Review batch %s sent to %d channel(s) in guild %s", batch_id, len(sent_messages), guild.id)
        else:
            logger.warning("[REVIEW] Review batch generated but no review channels responded for guild %s", guild.id)
        
        self._active_batches.pop(guild.id, None)
        return len(sent_messages) > 0
    
    
    @staticmethod
    def validate_review_channels(settings: GuildSettings) -> bool:
        """
        Check if guild has review channels configured.
        
        Args:
            settings: Guild settings to check
        
        Returns:
            bool: True if review channels are configured, False otherwise
        """
        return settings is not None and len(settings.review_channel_ids) > 0
