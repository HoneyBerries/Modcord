
"""
Moderation helper functions for global, multi-channel AI moderation.

This module orchestrates the batching of messages from multiple channels, applies per-channel server rules and dynamic JSON schemas,
and routes the results of AI moderation actions back to the appropriate Discord channels.

Key features:
- Groups messages per channel, but processes all channels together in a global batch for maximum throughput.
- Dynamically builds and applies per-channel guided decoding schemas (JSON schema/grammar) for each batch.
- Applies moderation actions and updates message history per channel.
"""

from typing import Dict, List

import discord

from modcord.ai.ai_moderation_processor import moderation_processor, model_state
from modcord.configuration.guild_settings import guild_settings_manager
from modcord.history.history_cache import global_history_cache_manager
from modcord.moderation.moderation_datatypes import ActionData, ActionType, ModerationChannelBatch
from modcord.util import discord_utils
from modcord.util.logger import get_logger

logger = get_logger("moderation_helper")


async def process_message_batches(self, batches: List[ModerationChannelBatch]) -> None:
    """
    Process multiple channel batches through the AI moderation pipeline globally.

    This function is called by the global batch timer. It receives a list of ModerationChannelBatch objects,
    each representing a group of messages from a single channel. It then:
    - Filters out empty or disabled batches.
    - Collects per-channel server rules to build a server_rules_map.
    - Passes all valid batches and their rules to the AI moderation processor, which builds a dynamic JSON schema/grammar for each channel.
    - Receives and applies moderation actions per channel.
    - Updates message history for each processed message.

    Args:
        batches (List[ModerationChannelBatch]): List of message batches, one per channel.
    """
    if not batches:
        return

    if not model_state.available:
        logger.debug("AI model unavailable: %s", model_state.init_error or "not initialized")
        return


    # Collect valid batches and build a map of channel_id -> server rules (for per-channel schema)
    valid_batches: List[ModerationChannelBatch] = []
    server_rules_map: Dict[int, str] = {}


    for batch in batches:
        # Skip empty batches or those with no messages
        if batch.is_empty() or not batch.messages:
            continue

        first_message = batch.messages[0]
        guild_id = first_message.guild_id
        # Skip channels where AI moderation is disabled
        if guild_id and not guild_settings_manager.is_ai_enabled(guild_id):
            logger.debug("AI moderation disabled for guild %s; skipping channel %s", guild_id, batch.channel_id)
            continue

        # Fetch per-channel server rules (used to build dynamic JSON schema/grammar)
        rules_text = guild_settings_manager.get_server_rules(guild_id) if guild_id else ""
        server_rules_map[batch.channel_id] = rules_text
        valid_batches.append(batch)

    if not valid_batches:
        return


    # Run all valid batches through the AI moderation processor in a single global batch call.
    # Each channel gets its own dynamic schema/grammar for guided decoding.
    actions_by_channel = await moderation_processor.get_multi_batch_moderation_actions(
        batches=valid_batches,
        server_rules_map=server_rules_map,
    )


    for batch in valid_batches:
        # Retrieve moderation actions for this channel (if any)
        actions = actions_by_channel.get(batch.channel_id, [])
        actionable_actions = [action for action in actions if action.action is not ActionType.NULL]

        # Apply each actionable moderation decision (e.g., warn, mute, ban)
        for action in actionable_actions:
            await apply_batch_action(self, action, batch)

        # Store all processed messages in channel history for future context
        for message in batch.messages:
            global_history_cache_manager.add_message(batch.channel_id, message)


async def apply_batch_action(self, action: ActionData, batch: ModerationChannelBatch) -> bool:
    """
    Execute a single moderation action produced by the AI for a given batch.

    This function checks permissions, finds the relevant Discord message, and applies the moderation action
    (such as warn, mute, or ban) to the user. It also ensures that actions are not applied to server owners or
    users with elevated permissions.

    Args:
        action (ActionData): The moderation action to apply.
        batch (ModerationChannelBatch): The batch of messages for the channel.

    Returns:
        bool: True if the action was successfully applied, False otherwise.
    """
    if action.action is ActionType.NULL or not action.user_id:
        return False


    # Find the most recent Discord message for the user in this batch
    user_messages = [m for m in batch.messages if m.user_id == action.user_id]
    pivot = next((m for m in reversed(user_messages) if m.discord_message), None)
    if not pivot or not pivot.discord_message:
        logger.warning(f"No Discord message for user {action.user_id}")
        return False

    # Check if the action is allowed for this guild
    guild_id = pivot.guild_id
    if guild_id and not guild_settings_manager.is_action_allowed(guild_id, action.action):
        return False

    msg = pivot.discord_message
    guild = msg.guild
    author = msg.author
    # Only apply actions to real members (not bots, not missing info)
    if not guild or not isinstance(author, discord.Member):
        return False

    # Never apply moderation to server owners or users with elevated permissions
    if guild.owner_id == author.id or discord_utils.has_elevated_permissions(author):
        return False

    # Build a lookup for all Discord messages in this batch (by message_id)
    msg_lookup = {str(m.message_id).strip(): m.discord_message for m in batch.messages if m.discord_message}


    try:
        # Actually apply the moderation action (warn, mute, ban, etc.)
        return await discord_utils.apply_action_decision(
            action=action, pivot=pivot, bot_user=self.bot.user, bot_client=self.bot, message_lookup=msg_lookup
        )
    except discord.Forbidden as e:
        logger.warning(f"Permission error ({action.action.value}): {e}")
        return False
    except Exception as e:
        logger.error(f"Error applying action: {e}")
        return False
