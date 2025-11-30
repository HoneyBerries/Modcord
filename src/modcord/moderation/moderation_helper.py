"""
Moderation helper functions for global, multi-channel AI moderation.

This module orchestrates batching and processing of messages from multiple Discord channels,
applies per-channel server rules and dynamic JSON schemas/grammars, and routes AI moderation
actions back to the appropriate Discord channels.

Features:
- Groups messages per channel, processes all channels together in a global batch for throughput
- Dynamically builds and applies per-channel guided decoding schemas (JSON schema/grammar)
- Applies moderation actions back to Discord contexts
"""

import datetime
from typing import List
import discord

from modcord.ai.ai_moderation_processor import moderation_processor, model_state
from modcord.settings.guild_settings_manager import guild_settings_manager
from modcord.database.database import get_db
from modcord.datatypes.action_datatypes import ActionData, ActionType
from modcord.datatypes.discord_datatypes import GuildID, UserID
from modcord.datatypes.moderation_datatypes import ModerationChannelBatch, ModerationUser
from modcord.moderation.human_review_manager import HumanReviewManager
from modcord.ui.action_embed import create_punishment_embed
from modcord.scheduler.unban_scheduler import UNBAN_SCHEDULER
from modcord.util.discord import discord_utils
from modcord.util.logger import get_logger


logger = get_logger("moderation_helper")


class ModerationEngine:
    """
    Engine for processing moderation batches through the AI pipeline.
    
    This class owns the batch processing logic and coordinates between
    the AI moderation processor and Discord action execution.
    
    Attributes:
        bot: The Discord bot instance for API access.
    """
    
    def __init__(self, bot: discord.Bot) -> None:
        """
        Initialize the moderation engine.
        
        Args:
            bot: Discord bot instance for API access and guild lookups.
        """
        self._bot = bot
    
    @property
    def bot(self) -> discord.Bot:
        """Get the Discord bot instance."""
        return self._bot
    
    async def process_batches(self, batches: List[ModerationChannelBatch]) -> None:
        """
        Process multiple channel batches through the AI moderation pipeline.
        
        This is the main entry point for batch processing. It:
        1. Filters batches based on AI moderation settings
        2. Prepares server rules and channel guidelines for each batch
        3. Sends all batches to the AI for inference
        4. Routes resulting actions to appropriate handlers
        
        Args:
            batches: List of ModerationChannelBatch objects to process.
        """
        if not batches or not model_state.available:
            return

        valid_batches = []
        guild_id = None

        # Filter batches based on AI moderation settings and prepare guild context
        for batch in batches:
            if batch.is_empty():
                continue
            
            first_user = batch.users[0]
            first_message = first_user.messages[0]

            guild_id = first_message.guild_id

            if not first_message or (guild_id and not guild_settings_manager.get(guild_id).ai_enabled):
                continue

            valid_batches.append(batch)

        if not valid_batches:
            logger.error("No valid batches to process for moderation.")
            return

        if guild_id is None:
            logger.error("No valid guild_id found for moderation batch processing.")
            return

        actions_by_channel = await moderation_processor.get_multi_batch_moderation_actions(
            batches=valid_batches,
            guild_id=guild_id
        )

        # Initialize review notification manager
        review_manager = HumanReviewManager(self._bot)
        
        # Track guilds that have review actions for batch finalization
        guilds_with_reviews = set()

        for batch in valid_batches:
            actions = actions_by_channel.get(batch.channel_id, [])
            for action in actions:
                if action.action is ActionType.NULL:
                    continue
                
                # Handle REVIEW actions separately through HumanReviewManager
                if action.action is ActionType.REVIEW:
                    await self._handle_review_action(action, batch, review_manager)
                    # Track guild for batch finalization
                    first_message = batch.users[0].messages[0] if batch.users and batch.users[0].messages else None
                    if first_message and first_message.guild_id:
                        guilds_with_reviews.add(first_message.guild_id)
                else:
                    await self._apply_batch_action(action, batch)
        
        # Finalize all review batches after processing all actions
        for guild_id in guilds_with_reviews:
            guild = self._bot.get_guild(guild_id)
            if guild:
                settings = guild_settings_manager.get(guild_id)
                if settings:
                    await review_manager.send_review_embed(guild, settings)

    async def _handle_review_action(
        self,
        action: ActionData,
        batch: ModerationChannelBatch,
        review_manager: HumanReviewManager
    ) -> bool:
        """
        Handle a REVIEW action by adding it to the HumanReviewManager.
        
        Args:
            action: Review action to handle.
            batch: Batch containing the user and messages.
            review_manager: HumanReviewManager instance for this batch.
        
        Returns:
            True if review item was successfully added, False otherwise.
        """
        logger.debug(
            "[MODERATION ENGINE] Processing review action for user %s in channel %s",
            action.user_id,
            batch.channel_id
        )
        
        if not action.user_id:
            logger.debug("[MODERATION ENGINE] Skipping: no user_id")
            return False
        
        # Find target user with Discord context
        target_user = find_target_user_in_batch(batch, action.user_id)
        if target_user is None:
            return False
        
        guild = target_user.discord_guild
        member = target_user.discord_member
        
        # Skip if user has elevated permissions
        if guild.owner_id == member.id or discord_utils.has_elevated_permissions(member):
            logger.debug(
                "[MODERATION ENGINE] Skipping review for user %s: elevated permissions",
                action.user_id
            )
            return False
        
        # Add review item to the manager
        try:
            await review_manager.add_item_for_review(
                guild=guild,
                user=target_user,
                action=action
            )
            logger.info(
                "[MODERATION ENGINE] Added review item for user %s in guild %s",
                action.user_id,
                guild.id
            )
            return True
        except Exception as e:
            logger.error(
                "[MODERATION ENGINE] Failed to add review item for user %s: %s",
                action.user_id,
                e,
                exc_info=True
            )
            return False

    async def _apply_batch_action(
        self,
        action: ActionData,
        batch: ModerationChannelBatch
    ) -> bool:
        """
        Apply a moderation action to a user in the batch.
        
        Args:
            action: ActionData containing action type and parameters.
            batch: Batch containing the target user.
        
        Returns:
            True if action was successfully applied, False otherwise.
        """
        logger.debug(
            "[MODERATION ENGINE] Applying action %s for user %s in channel %s",
            action.action.value,
            action.user_id,
            batch.channel_id
        )
        
        if action.action is ActionType.NULL or not action.user_id:
            logger.debug("[MODERATION ENGINE] Skipping: action is NULL or no user_id")
            return False

        # Find target user with Discord context
        target_user = find_target_user_in_batch(batch, action.user_id)
        if target_user is None:
            logger.warning(
                "[MODERATION ENGINE] Batch has %d users: %s",
                len(batch.users),
                [str(u.user_id) for u in batch.users]
            )
            return False

        guild = target_user.discord_guild
        member = target_user.discord_member

        guild_id = GuildID.from_guild(guild)

        if not guild_settings_manager.is_action_allowed(guild_id, action.action):
            logger.warning(
                "[MODERATION ENGINE] Action %s not allowed in guild %s",
                action.action.value,
                guild_id.to_int()
            )
            return False

        if guild.owner_id == member.id or discord_utils.has_elevated_permissions(member):
            logger.debug(
                "[MODERATION ENGINE] Skipping action for user %s: elevated permissions",
                action.user_id
            )
            return False

        try:
            # Fetch the Discord channel to pass to action execution
            channel = None
            try:
                channel = guild.get_channel(batch.channel_id.to_int())
            except (ValueError, TypeError, AttributeError):
                logger.warning(f"Could not fetch channel {batch.channel_id}")
            
            if channel is None or not isinstance(channel, discord.TextChannel):
                logger.warning(
                    "[MODERATION ENGINE] Channel %s not found or invalid in guild %s",
                    batch.channel_id,
                    guild_id
                )
                return False
            
            result = await apply_action_decision(
                action=action,
                member=member,
                guild=guild,
                bot_client=self._bot,
                channel=channel
            )
            logger.info(
                "[MODERATION ENGINE] Applied action %s for user %s: %s",
                action.action.value,
                action.user_id,
                result
            )
            return result
        except discord.Forbidden:
            logger.warning(
                "Permission error applying action %s for user %s",
                action.action.value,
                action.user_id
            )
            return False
        except Exception as e:
            logger.error(
                "Error applying action %s for user %s: %s",
                action.action.value,
                action.user_id,
                e,
                exc_info=True
            )
            return False


# ---------------------------------------------------------------------------
# Utility functions (stateless)
# ---------------------------------------------------------------------------

def find_target_user_in_batch(
    batch: ModerationChannelBatch,
    user_id: UserID
) -> ModerationUser | None:
    """
    Find a target user in a batch by user ID.
    
    Args:
        batch: ModerationChannelBatch to search.
        user_id: UserID to find.
    
    Returns:
        ModerationUser if found with valid Discord context, None otherwise.
    """
    target_user = next((u for u in batch.users if u.user_id == user_id), None)
    
    if not target_user or not target_user.messages:
        logger.warning(
            "[MODERATION HELPER] Target user %s not found in batch or has no messages",
            user_id
        )
        return None
    
    if not target_user.discord_member or not target_user.discord_guild:
        logger.warning(
            "[MODERATION HELPER] Target user %s missing Discord context",
            user_id
        )
        return None
    
    return target_user


async def execute_moderation_notification(
    action_type: ActionType,
    user: discord.Member,
    guild: discord.Guild,
    reason: str,
    channel: discord.TextChannel,
    bot_user: discord.User | discord.ClientUser,
    duration: datetime.timedelta | None = None,
) -> None:
    """
    Send moderation notification embed to user via DM and optionally to channel.
    
    Args:
        action_type: Type of moderation action
        user: Target user
        guild: Guild context
        reason: Reason for action
        duration: Optional duration timedelta (for timeout/ban)
        channel: Optional channel to post embed in
        bot_user: Optional bot user for footer attribution
    """
    embed = await create_punishment_embed(
        action_type,
        user,
        guild,
        reason,
        admin=bot_user,
        duration=duration)
    
    # Try to send DM
    try:
        await user.send(embed=embed)
    except discord.Forbidden:
        logger.debug(f"Cannot send DM to user {user.id}: DMs disabled")
    except Exception as e:
        logger.error(f"Error sending DM to {user.id}: {e}")
    

    # Post to channel if the channel exists
    if channel:
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            logger.warning(f"Cannot post to channel {channel.id}: missing permissions")
        except Exception as e:
            logger.error(f"Error posting to channel {channel.id}: {e}")


async def apply_action_decision(
    action: ActionData,
    member: discord.Member,
    guild: discord.Guild,
    bot_client: discord.Bot,
    channel: discord.TextChannel | None,
) -> bool:
    """
    Apply a moderation action decision to a user.
    
    Args:
        action: ActionData containing action type and parameters
        member: Discord member to apply action to
        guild: Discord guild context
        bot_client: Bot instance for API calls
        channel: Optional Discord channel to post notification embed to
    
    Returns:
        bool: True if action was successfully applied
    """
    # Delete messages if specified
    if action.message_ids:
        await discord_utils.delete_messages_by_ids(guild, action.message_ids)
    
    if bot_client is None or bot_client.user is None:
        logger.error("Bot client is None or bot user is None, cannot apply moderation action")
        return False
    
    if channel is None:
        logger.error("Channel is None or missing, cannot apply moderation action")
        return False
    
    # Apply action
    try:
        if action.action == ActionType.WARN:
            await execute_moderation_notification(
                action_type=ActionType.WARN,
                user=member,
                guild=guild,
                reason=action.reason,
                channel=channel,
                bot_user=bot_client.user,
            )
            await get_db().log_moderation_action(action)
            return True
        
        elif action.action == ActionType.DELETE:
            # Messages already deleted above
            await get_db().log_moderation_action(action)
            return True
        
        elif action.action == ActionType.TIMEOUT:
            duration_minutes = action.timeout_duration or 10
            if duration_minutes == -1:
                duration_minutes = 28 * 24 * 60  # Cap to Discord's max
            duration = datetime.timedelta(minutes=duration_minutes)
            until = discord.utils.utcnow() + duration
            
            await member.timeout(until, reason=f"ModCord: {action.reason}")
            await execute_moderation_notification(
                action_type=ActionType.TIMEOUT,
                user=member,
                guild=guild,
                reason=action.reason,
                duration=duration,
                channel=channel,
                bot_user=bot_client.user
            )
            await get_db().log_moderation_action(action)
            return True
        
        elif action.action == ActionType.KICK:
            await guild.kick(member, reason=f"ModCord: {action.reason}")
            await execute_moderation_notification(
                action_type=ActionType.KICK,
                user=member,
                guild=guild,
                reason=action.reason,
                channel=channel,
                bot_user=bot_client.user,
            )
            await get_db().log_moderation_action(action)
            return True
        
        elif action.action == ActionType.BAN:
            duration_minutes = action.ban_duration or 0
            is_permanent = duration_minutes <= 0
            duration = None if is_permanent else datetime.timedelta(minutes=duration_minutes)
            
            await guild.ban(member, reason=f"ModCord: {action.reason}")
            
            # Schedule unban if not permanent
            if duration is not None:
                try:
                    await UNBAN_SCHEDULER.schedule(
                        guild=guild,
                        user_id=UserID(str(member.id)),
                        channel=None,
                        duration_seconds=int(duration.total_seconds()),
                        bot=bot_client,
                        reason="Ban duration expired.",
                    )
                except Exception as e:
                    logger.error(f"Failed to schedule unban for user {member.id}: {e}")
            
            await execute_moderation_notification(
                action_type=ActionType.BAN,
                user=member,
                guild=guild,
                reason=action.reason,
                duration=duration,
                channel=channel,
                bot_user=bot_client.user,
            )
            await get_db().log_moderation_action(action)
            return True
        
        else:
            return False
    
    except discord.Forbidden:
        logger.warning(f"Permission denied applying {action.action.value} to {member.id} in {guild.id}")
        return False
    except Exception as e:
        logger.error(f"Error applying {action.action.value}: {e}", exc_info=True)
        return False