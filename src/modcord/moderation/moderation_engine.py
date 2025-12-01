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

from typing import List
import discord

from modcord.ai.ai_moderation_processor import moderation_processor, model_state
from modcord.settings.guild_settings_manager import guild_settings_manager
from modcord.datatypes.action_datatypes import ActionData, ActionType
from modcord.datatypes.discord_datatypes import GuildID
from modcord.datatypes.moderation_datatypes import ModerationChannelBatch
from modcord.moderation.human_review_manager import HumanReviewManager
from modcord.moderation import moderation_helper
from modcord.util.discord import discord_utils
from modcord.util.logger import get_logger


logger = get_logger("moderation_engine")


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
        target_user = moderation_helper.find_target_user_in_batch(batch, action.user_id)
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
        target_user = moderation_helper.find_target_user_in_batch(batch, action.user_id)
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
            
            action_data = ActionData(
                guild_id=action.guild_id,
                channel_id=batch.channel_id,
                user_id=action.user_id,
                action=action.action,
                reason=action.reason,
                timeout_duration=action.timeout_duration,
                ban_duration=action.ban_duration,
                message_ids_to_delete=action.message_ids_to_delete,
            )
            
            result = await moderation_helper.apply_action_decision(
                action=action_data,
                member=member,
                bot=self._bot)
            
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
                exc_info=True)
            return False