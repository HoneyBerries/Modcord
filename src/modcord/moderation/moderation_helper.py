"""Moderation helper functions used by the event listener."""

import discord
from typing import List, Dict

from modcord.ai.ai_moderation_processor import model_state, moderation_processor
from modcord.configuration.guild_settings import guild_settings_manager
from modcord.moderation.moderation_datatypes import ActionData, ActionType, ModerationChannelBatch
from modcord.util import discord_utils
from modcord.util.logger import get_logger

logger = get_logger("moderation_helper")


async def process_message_batches(self, batches: List[ModerationChannelBatch]) -> None:
    """Process multiple channel batches through the AI moderation pipeline globally."""
    if not batches:
        return

    # Filter out empty batches
    non_empty_batches = [b for b in batches if not b.is_empty()]
    if not non_empty_batches:
        return

    # Check if AI is enabled for the first batch's guild (assuming all from same context)
    first_message = non_empty_batches[0].messages[0]
    guild_id = first_message.guild_id
    if guild_id and not guild_settings_manager.is_ai_enabled(guild_id):
        return

    if not model_state.available:
        logger.debug(f"AI model unavailable: {model_state.init_error or 'not initialized'}")
        return

    # Process batches and collect actions per channel
    server_rules = guild_settings_manager.get_server_rules(guild_id) if guild_id else ""
    all_actions = await moderation_processor.get_multi_batch_moderation_actions(
        batches=non_empty_batches,
        server_rules=server_rules
    )

    # Apply actions grouped by channel
    for channel_id, actions in all_actions.items():
        # Find the corresponding batch
        channel_batch = next((b for b in non_empty_batches if b.channel_id == channel_id), None)
        if not channel_batch:
            continue

        actionable_actions = [a for a in actions if a.action is not ActionType.NULL]
        for action in actionable_actions:
            await apply_batch_action(self, action, channel_batch)


async def apply_batch_action(self, action: ActionData, batch: ModerationChannelBatch) -> bool:
    """Execute a single moderation action produced by the AI."""
    if action.action is ActionType.NULL or not action.user_id:
        return False

    user_messages = [m for m in batch.messages if m.user_id == action.user_id]
    pivot = next((m for m in reversed(user_messages) if m.discord_message), None)
    if not pivot or not pivot.discord_message:
        logger.warning(f"No Discord message for user {action.user_id}")
        return False

    guild_id = pivot.guild_id
    if guild_id and not guild_settings_manager.is_action_allowed(guild_id, action.action):
        return False

    msg = pivot.discord_message
    guild = msg.guild
    author = msg.author
    if not guild or not isinstance(author, discord.Member):
        return False

    if guild.owner_id == author.id or discord_utils.has_elevated_permissions(author):
        return False

    msg_lookup = {str(m.message_id).strip(): m.discord_message for m in batch.messages if m.discord_message}

    try:
        return await discord_utils.apply_action_decision(
            action=action, pivot=pivot, bot_user=self.bot.user, bot_client=self.bot, message_lookup=msg_lookup
        )
    except discord.Forbidden as e:
        logger.warning(f"Permission error ({action.action.value}): {e}")
        return False
    except Exception as e:
        logger.error(f"Error applying action: {e}")
        return False
