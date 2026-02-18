"""
Moderation pipeline for server-wide AI moderation.

This module orchestrates the full moderation flow:
- Validates the server batch (non-empty, AI enabled)
- Gets AI moderation decisions via LLMEngine (single request per guild)
- Routes actions to Discord (delete, timeout, kick, ban) or human review

Features:
- Single ServerModerationBatch per guild per batch interval
- Server-wide AI inference (all channels in one request)
- Applies moderation actions back to Discord contexts
"""

from typing import List
import discord

from modcord.ai.llm_engine import LLMEngine
from modcord.settings.guild_settings_manager import guild_settings_manager
from modcord.datatypes.action_datatypes import ActionData, ActionType
from modcord.datatypes.discord_datatypes import GuildID
from modcord.datatypes.moderation_datatypes import ServerModerationBatch
from modcord.moderation.human_review_manager import HumanReviewManager
from modcord.moderation import moderation_helper
from modcord.util.discord import discord_utils
from modcord.util.logger import get_logger


logger = get_logger("moderation_engine")

llm_engine = LLMEngine()


class ModerationPipeline:
    """
    Engine for processing server-wide moderation batches through the AI pipeline.
    
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
    
    async def execute(self, batch: ServerModerationBatch) -> None:
        """
        Execute the full moderation pipeline: AI inference + action application.
        
        Flow:
        1. Validate batch (non-empty, AI enabled)
        2. Get AI moderation decisions via LLMEngine (single request)
        3. Apply actions (delete, timeout, kick, ban) or queue for review
        
        Args:
            batch: ServerModerationBatch containing all users/messages across channels.
        """
        if batch.is_empty():
            return

        # Check if AI moderation is enabled for this guild
        settings = await guild_settings_manager.get_settings(batch.guild_id)
        if settings and not settings.ai_enabled:
            logger.info("[PIPELINE] AI moderation disabled for guild %s", batch.guild_id)
            return

        # Get AI moderation decisions (single request for the whole server batch)
        actions = await llm_engine.get_moderation_actions(batch)

        if not actions:
            logger.debug("[PIPELINE] No actions returned for guild %s", batch.guild_id)
            return

        # Apply actions and handle reviews
        review_manager = HumanReviewManager(self._bot)
        has_reviews = False

        for action in actions:
            if action.action is ActionType.NULL:
                continue
            
            # Handle REVIEW actions separately through HumanReviewManager
            if action.action is ActionType.REVIEW:
                result = await self._handle_review_action(action, batch, review_manager)
                if result:
                    has_reviews = True
            else:
                await self._apply_batch_action(action, batch)
        
        # Finalize all review batches after processing all actions
        if has_reviews:
            guild = self._bot.get_guild(batch.guild_id.to_int())
            if guild and settings:
                await review_manager.send_review_embed(guild, settings)


    async def _handle_review_action(
        self,
        action: ActionData,
        batch: ServerModerationBatch,
        review_manager: HumanReviewManager
    ) -> bool:
        """
        Handle a REVIEW action by adding it to the HumanReviewManager.
        
        Args:
            action: Review action to handle.
            batch: Server batch containing the user and messages.
            review_manager: HumanReviewManager instance for this batch.
        
        Returns:
            True if review item was successfully added, False otherwise.
        """
        logger.debug(
            "[PIPELINE] Processing review action for user %s in guild %s",
            action.user_id,
            batch.guild_id
        )
        
        if not action.user_id:
            logger.debug("[PIPELINE] Skipping: no user_id")
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
                "[PIPELINE] Skipping review for user %s: elevated permissions",
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
                "[PIPELINE] Added review item for user %s in guild %s",
                action.user_id,
                guild.id
            )
            return True
        except Exception as e:
            logger.error(
                "[PIPELINE] Failed to add review item for user %s: %s",
                action.user_id,
                e,
                exc_info=True
            )
            return False

    async def _apply_batch_action(
        self,
        action: ActionData,
        batch: ServerModerationBatch
    ) -> bool:
        """
        Apply a moderation action to a user in the batch.
        
        Args:
            action: ActionData containing action type and parameters.
            batch: Server batch containing the target user.
        
        Returns:
            True if action was successfully applied, False otherwise.
        """
        logger.debug(
            "[PIPELINE] Applying action %s for user %s in guild %s",
            action.action.value,
            action.user_id,
            batch.guild_id
        )
        
        if action.action is ActionType.NULL or not action.user_id:
            logger.debug("[PIPELINE] Skipping: action is NULL or no user_id")
            return False

        # Find target user with Discord context
        target_user = moderation_helper.find_target_user_in_batch(batch, action.user_id)
        if target_user is None:
            logger.warning(
                "[PIPELINE] Batch has %d users: %s",
                len(batch.users),
                [str(u.user_id) for u in batch.users]
            )
            return False

        guild = target_user.discord_guild
        member = target_user.discord_member

        guild_id = GuildID.from_guild(guild)

        if not guild_settings_manager.is_action_allowed(guild_id, action.action):
            logger.warning(
                "[PIPELINE] Action %s not allowed in guild %s",
                action.action.value,
                guild_id.to_int()
            )
            return False

        if guild.owner_id == member.id or discord_utils.has_elevated_permissions(member):
            logger.debug(
                "[PIPELINE] Skipping action for user %s: elevated permissions",
                action.user_id
            )
            return False

        try:
            # Derive notification channel from the user's first message in the batch
            notification_channel = _resolve_notification_channel(guild, batch, target_user)
            
            result = await moderation_helper.apply_action(
                action=action,
                member=member,
                bot=self._bot,
                notification_channel=notification_channel,
            )
            
            logger.debug(
                "[PIPELINE] Applied action %s for user %s: %s",
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


def _resolve_notification_channel(
    guild: discord.Guild,
    batch: ServerModerationBatch,
    target_user,
) -> discord.TextChannel | None:
    """Derive the best channel to post a notification embed in.
    
    Strategy: use the channel of the user's first message in the batch.
    Falls back to the first channel in the batch if the user's messages
    don't resolve to a valid text channel.
    
    Args:
        guild: Discord guild object.
        batch: Server batch with channel metadata.
        target_user: ModerationUser whose messages we inspect.
    
    Returns:
        A TextChannel if one can be resolved, otherwise None.
    """
    # Try the channel of the user's first message
    if target_user.messages:
        first_msg = target_user.messages[0]
        ch = guild.get_channel(first_msg.channel_id.to_int())
        if isinstance(ch, discord.TextChannel):
            return ch

    # Fallback: first channel in the batch
    for ctx in batch.channels.values():
        ch = guild.get_channel(ctx.channel_id.to_int())
        if isinstance(ch, discord.TextChannel):
            return ch

    return None