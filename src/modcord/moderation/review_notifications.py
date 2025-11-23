"""
Human moderator review notification system.

This module manages the creation and tracking of review requests that require
human moderator intervention. It consolidates multiple review actions per batch
into a single embed to prevent spam and provides persistent tracking of review status.

Key Features:
- Batch consolidation: Groups all review actions per batch into one embed per guild
- Persistent tracking: Stores review requests in database with status tracking
- Interactive UI: Integrates with ReviewResolutionView for button interactions
- User context: Includes past moderation history in review embeds
"""

from __future__ import annotations

import discord
from typing import TYPE_CHECKING, List
from dataclasses import dataclass
from datetime import datetime, timezone
import uuid

from modcord.util.logger import get_logger
from modcord.database.database import get_connection, get_past_actions
from modcord.moderation.moderation_datatypes import ActionData, ActionType, format_past_actions

if TYPE_CHECKING:
    from modcord.configuration.guild_settings import GuildSettings

logger = get_logger("review_notifications")


@dataclass
class ReviewItem:
    """
    Single review item representing one user's flagged content.
    
    Attributes:
        user: Discord member object for the flagged user
        reason: AI-generated reason for flagging
        message: Original Discord message that was flagged
        past_actions: List of formatted past moderation actions for context
    """
    user: discord.Member
    reason: str
    message: discord.Message
    past_actions: List[dict]


class ReviewNotificationManager:
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
        self._active_batches: dict[int, List[ReviewItem]] = {}  # guild_id -> list of review items
    
    async def add_item_to_review(
        self,
        guild: discord.Guild,
        user: discord.Member,
        message: discord.Message,
        action: ActionData
    ) -> None:
        """
        Add a review item to the current batch for this guild.
        
        Items are accumulated per guild and will be sent together when send_review_batch_embed is called.
        
        Args:
            guild: Discord guild where the review is needed
            user: User whose content was flagged
            message: Message that triggered the review
            action: ActionData containing the review reason
        """
        # Fetch user's past actions for context
        past_actions_raw = await get_past_actions(
            guild_id=guild.id,
            user_id=str(user.id),
            lookback_minutes=10080  # 7 days
        )
        past_actions = format_past_actions(past_actions_raw)
        
        review_item = ReviewItem(
            user=user,
            reason=action.reason,
            message=message,
            past_actions=past_actions
        )
        
        if guild.id not in self._active_batches:
            self._active_batches[guild.id] = []
        
        self._active_batches[guild.id].append(review_item)
        logger.debug("[REVIEW] Added review item for user %s in guild %s", user.id, guild.id)
    
    async def send_review_batch_embed(self, guild: discord.Guild, settings: GuildSettings) -> bool:
        """
        Finalize and send the consolidated review embed for this guild's batch.
        
        Creates a single embed containing all review items for this batch,
        sends it to all configured review channels, and stores the review
        request in the database for tracking.
        
        Args:
            guild: Discord guild to finalize reviews for
            settings: Guild settings containing review channel configuration
        
        Returns:
            bool: True if review was successfully sent, False otherwise
        """
        if guild.id not in self._active_batches or not self._active_batches[guild.id]:
            logger.debug("[REVIEW] No review items to finalize for guild %s", guild.id)
            return False
        
        review_items = self._active_batches[guild.id]
        batch_id = str(uuid.uuid4())
        
        # Build consolidated embed
        embed = self._build_review_embed(review_items, batch_id)
        
        # Send to all review channels
        sent_messages = await self._send_to_review_channels(
            guild=guild,
            settings=settings,
            batch_id=batch_id,
            embed=embed
        )
        
        # Store all review messages if successfully sent
        if sent_messages:
            await self.store_review_requests_to_database(
                batch_id=batch_id,
                guild_id=guild.id,
                messages=sent_messages
            )
            logger.info("[REVIEW] Review batch %s sent to %d channel(s) in guild %s", batch_id, len(sent_messages), guild.id)
        else:
            logger.warning("[REVIEW] Review batch generated but no review channels responded for guild %s", guild.id)
        
        # Clear batch for this guild
        del self._active_batches[guild.id]
        
        return len(sent_messages) > 0
    
    def _build_review_embed(self, review_items: List[ReviewItem], batch_id: str) -> discord.Embed:
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
            # Build user field with context
            user_info = f"**User:** {item.user.mention} (`{item.user.id}`)\n"
            
            # Add channel mention (handle different channel types)
            channel_mention = getattr(item.message.channel, 'mention', None)
            if channel_mention:
                user_info += f"**Channel:** {channel_mention}\n"
            else:
                user_info += f"**Channel:** <#{item.message.channel.id}>\n"
            
            user_info += f"**Reason:** {item.reason}\n"
            
            # Add message content if present
            if item.message.content:
                content_preview = item.message.content[:200]
                if len(item.message.content) > 200:
                    content_preview += "..."
                user_info += f"**Message:** {content_preview}\n"
            
            # Add message link
            user_info += f"**[Jump to Message]({item.message.jump_url})**\n"
            
            # Add past actions context if any
            if item.past_actions:
                past_actions_str = ", ".join(
                    f"{act['action']}" for act in item.past_actions[:3]
                )
                if len(item.past_actions) > 3:
                    past_actions_str += f" (+{len(item.past_actions) - 3} more)"
                user_info += f"**History (7d):** {past_actions_str}"
            else:
                user_info += "**History (7d):** No prior actions"
            
            # Add field for this user
            embed.add_field(
                name=f"#{idx}: {item.user.display_name}",
                value=user_info,
                inline=False
            )
        
        # Add footer with batch ID and bot info
        if self.bot.user:
            embed.set_footer(text=f"Bot: {self.bot.user.name} | Batch: {batch_id[:8]}")
        else:
            embed.set_footer(text=f"Batch: {batch_id[:8]}")
        
        # Add first image if available
        for item in review_items:
            if item.message.attachments:
                from modcord.util.discord_utils import is_image_attachment
                img_attachments = [a for a in item.message.attachments if is_image_attachment(a)]
                if img_attachments:
                    embed.set_image(url=img_attachments[0].url)
                    break
        
        return embed
    
    async def _send_to_review_channels(
        self,
        guild: discord.Guild,
        settings: GuildSettings,
        batch_id: str,
        embed: discord.Embed
    ) -> List[tuple[int, int]]:
        """
        Send review embed to all configured review channels.
        
        Args:
            guild: Discord guild to send to
            settings: Guild settings containing review channel IDs
            batch_id: Unique identifier for this review batch
            embed: Review embed to send
        
        Returns:
            List[tuple[int, int]]: List of (channel_id, message_id) tuples for all sent messages
        """
        sent_messages = []
        
        # Import here to avoid circular dependency
        from modcord.bot.review_ui import ReviewResolutionView
        
        for channel_id in settings.review_channel_ids:
            review_channel = guild.get_channel(channel_id)
            if review_channel and isinstance(review_channel, (discord.TextChannel, discord.Thread)):
                try:
                    view = ReviewResolutionView(batch_id=batch_id, guild_id=guild.id, bot=self.bot)
                    mention_content = self.build_role_mentions(guild, settings)
                    
                    sent_message = await review_channel.send(
                        content=mention_content,
                        embed=embed,
                        view=view
                    )
                    sent_messages.append((channel_id, sent_message.id))
                    logger.info("[REVIEW] Sent review batch %s to channel %s", batch_id, channel_id)
                except Exception as e:
                    logger.error("[REVIEW] Failed to send review to channel %s: %s", channel_id, e)
        
        return sent_messages
    
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
    
    @staticmethod
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
    
    async def store_review_requests_to_database(
        self,
        batch_id: str,
        guild_id: int,
        messages: List[tuple[int, int]]
    ) -> None:
        """
        Store multiple review request messages in the database.
        
        Args:
            batch_id: Unique identifier for this review batch
            guild_id: ID of the guild where the review was sent
            messages: List of (channel_id, message_id) tuples
        """
        try:
            async with get_connection() as db:
                for channel_id, message_id in messages:
                    await db.execute(
                        """
                        INSERT INTO review_requests (batch_id, guild_id, channel_id, message_id, status)
                        VALUES (?, ?, ?, ?, 'pending')
                        """,
                        (batch_id, guild_id, channel_id, message_id)
                    )
                await db.commit()
            logger.debug("[REVIEW] Stored %d review messages for batch %s in database", len(messages), batch_id)
        except Exception as e:
            logger.error("[REVIEW] Failed to store review requests for batch %s: %s", batch_id, e)
    
    @staticmethod
    async def mark_resolved(
        batch_id: str,
        resolved_by: int,
        resolution_note: str | None = None
    ) -> bool:
        """
        Mark all review requests with this batch_id as resolved.
        
        Args:
            batch_id: Unique identifier of the review batch to resolve
            resolved_by: User ID of the moderator who resolved the review
            resolution_note: Optional note about the resolution
        
        Returns:
            bool: True if successfully marked as resolved, False otherwise
        """
        try:
            async with get_connection() as db:
                # Update all pending messages with this batch_id
                cursor = await db.execute(
                    """
                    UPDATE review_requests
                    SET status = 'resolved',
                        resolved_at = CURRENT_TIMESTAMP,
                        resolved_by = ?,
                        resolution_note = ?
                    WHERE batch_id = ? AND status = 'pending'
                    """,
                    (resolved_by, resolution_note, batch_id)
                )
                await db.commit()
                
                if cursor.rowcount > 0:
                    logger.info("[REVIEW] Review batch %s marked as resolved (%d messages) by user %s", batch_id, cursor.rowcount, resolved_by)
                    return True
                else:
                    logger.warning("[REVIEW] Review batch %s not found or already resolved", batch_id)
                    return False
        except Exception as e:
            logger.error("[REVIEW] Failed to mark review batch %s as resolved: %s", batch_id, e)
            return False
    
    @staticmethod
    async def get_batch_messages(batch_id: str) -> List[tuple[int, int, int]]:
        """
        Get all message references for a review batch.
        
        Args:
            batch_id: Unique identifier of the review batch
        
        Returns:
            List[tuple[int, int, int]]: List of (guild_id, channel_id, message_id) tuples
        """
        try:
            async with get_connection() as db:
                cursor = await db.execute(
                    """
                    SELECT guild_id, channel_id, message_id
                    FROM review_requests
                    WHERE batch_id = ? AND message_id IS NOT NULL
                    """,
                    (batch_id,)
                )
                rows = await cursor.fetchall()
                return [(row[0], row[1], row[2]) for row in rows]
        except Exception as e:
            logger.error("[REVIEW] Failed to get batch messages for %s: %s", batch_id, e)
            return []
    
    @staticmethod
    async def get_review_status(batch_id: str) -> dict | None:
        """
        Get the status of a review request.
        
        Args:
            batch_id: Unique identifier of the review batch
        
        Returns:
            dict | None: Dictionary with status information, or None if not found
        """
        try:
            async with get_connection() as db:
                cursor = await db.execute(
                    """
                    SELECT status, created_at, resolved_at, resolved_by, resolution_note
                    FROM review_requests
                    WHERE batch_id = ?
                    """,
                    (batch_id,)
                )
                row = await cursor.fetchone()
                
                if row:
                    return {
                        "status": row[0],
                        "created_at": row[1],
                        "resolved_at": row[2],
                        "resolved_by": row[3],
                        "resolution_note": row[4]
                    }
                return None
        except Exception as e:
            logger.error("[REVIEW] Failed to get review status for batch %s: %s", batch_id, e)
            return None
