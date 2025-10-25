"""
Moderation helper functions for global, multi-channel AI moderation.

This module orchestrates batching and processing of messages from multiple Discord channels, applies per-channel server rules and dynamic JSON schemas/grammars, and routes AI moderation actions back to the appropriate Discord channels.

Features:
- Groups messages per channel, processes all channels together in a global batch for throughput
- Dynamically builds and applies per-channel guided decoding schemas (JSON schema/grammar)
- Applies moderation actions and updates message history per channel
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
    Process multiple channel batches through the AI moderation pipeline in a global batch.
    """
    if not batches or not model_state.available:
        return

    valid_batches = []
    server_rules_map = {}
    channel_guidelines_map = {}

    # Filter batches based on AI moderation settings and prepare rules/guidelines
    for batch in batches:
        if batch.is_empty():
            continue
        first_user = batch.users[0] if batch.users else None
        first_message = first_user.messages[0] if first_user and first_user.messages else None
        guild_id = first_message.guild_id if first_message else None
        if not first_message or (guild_id and not guild_settings_manager.is_ai_enabled(guild_id)):
            continue

        # Prepare server rules and channel guidelines
        server_rules_map[batch.channel_id] = guild_settings_manager.get_server_rules(guild_id) if guild_id else ""
        channel_guidelines_map[batch.channel_id] = guild_settings_manager.get_channel_guidelines(guild_id, batch.channel_id) if guild_id else ""
        valid_batches.append(batch)

    if not valid_batches:
        return

    actions_by_channel = await moderation_processor.get_multi_batch_moderation_actions(
        batches=valid_batches,
        server_rules_map=server_rules_map,
        channel_guidelines_map=channel_guidelines_map,
    )

    for batch in valid_batches:
        actions = actions_by_channel.get(batch.channel_id, [])
        for action in actions:
            if action.action is not ActionType.NULL:
                await apply_batch_action(self, action, batch)
        for user in batch.users:
            for message in user.messages:
                global_history_cache_manager.add_message(batch.channel_id, message)


async def apply_batch_action(self, action: ActionData, batch: ModerationChannelBatch) -> bool:
    """
    Apply a moderation action to a user in the batch, ensuring permissions and context.
    """
    if action.action is ActionType.NULL or not action.user_id:
        return False

    target_user = next((u for u in batch.users if u.user_id == action.user_id), None)
    if not target_user or not target_user.messages:
        return False

    pivot = next((m for m in reversed(target_user.messages) if m.discord_message), None)
    if not pivot or not pivot.discord_message:
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

    msg_lookup = {str(m.message_id).strip(): m.discord_message
                  for user in batch.users for m in user.messages if m.discord_message}

    try:
        return await discord_utils.apply_action_decision(
            action=action, pivot=pivot, bot_user=self.bot.user, bot_client=self.bot, message_lookup=msg_lookup
        )
    except discord.Forbidden:
        logger.warning(f"Permission error ({action.action.value})")
        return False
    except Exception as e:
        logger.error(f"Error applying action: {e}")
        return False