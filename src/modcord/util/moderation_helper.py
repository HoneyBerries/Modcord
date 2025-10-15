"""Moderation helper functions used by the event listener."""

import asyncio
import discord

from modcord.ai.ai_moderation_processor import model_state, moderation_processor
from modcord.configuration.guild_settings import guild_settings_manager
from modcord.bot import rules_manager
from modcord.util.moderation_datatypes import ActionData, ActionType, ModerationBatch, ModerationMessage
from modcord.util import discord_utils
from modcord.util.logger import get_logger

logger = get_logger("moderation_helper")


async def process_message_batch(self, batch: ModerationBatch) -> None:
    """Process a batch of messages through the AI moderation pipeline."""
    try:
        if batch.is_empty():
            return

        guild_id = batch.messages[0].guild_id
        if guild_id and not guild_settings_manager.is_ai_enabled(guild_id):
            return

        if not model_state.available:
            logger.debug(f"AI model unavailable: {model_state.init_error or 'not initialized'}")
            return

        server_rules = guild_settings_manager.get_server_rules(guild_id) if guild_id else ""
        actions = await moderation_processor.get_batch_moderation_actions(batch=batch, server_rules=server_rules)
        actionable_actions = [a for a in actions if a.action is not ActionType.NULL]

        # Build message ID lookup
        msg_lookup = {str(m.user_id): {str(msg.message_id) for msg in batch.messages if msg.user_id == m.user_id} for m in batch.messages}

        for action in actionable_actions:
            allowed_ids = msg_lookup.get(action.user_id, set())
            if action.message_ids:
                filtered = [mid for mid in action.message_ids if mid in allowed_ids]
                if len(filtered) != len(action.message_ids):
                    logger.warning(f"Filtered {len(action.message_ids) - len(filtered)} message IDs for user {action.user_id}")
                action.replace_message_ids(filtered)
            await apply_batch_action(self, action, batch)
    except Exception as e:
        logger.error(f"Error processing batch: {e}")


async def apply_batch_action(self, action: ActionData, batch: ModerationBatch) -> bool:
    """Execute a single moderation action produced by the AI."""
    try:
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
        except (discord.Forbidden) as e:
            logger.warning(f"Permission error ({action.action.value}): {e}")
            return False
    except Exception as e:
        logger.error(f"Error applying action: {e}")
        return False


async def refresh_rules_cache_if_rules_channel(channel: discord.abc.Messageable) -> None:
    """Refresh the rules cache when activity occurs in a rules channel."""
    if not isinstance(channel, discord.TextChannel) or not rules_manager.RULE_CHANNEL_PATTERN.search(channel.name or ""):
        return
    guild = channel.guild
    if not guild:
        return
    try:
        await rules_manager.refresh_guild_rules(guild, settings=guild_settings_manager)
        logger.info(f"Rules refreshed in {channel.name}")
    except Exception as e:
        logger.error(f"Failed to refresh rules: {e}")


async def refresh_rules_cache_task(self):
    """Background task that periodically refreshes the cached server rules."""
    try:
        await rules_manager.run_periodic_refresh(self.bot, settings=guild_settings_manager)
    except asyncio.CancelledError:
        logger.info("Rules refresh task cancelled")
        raise
    except Exception as e:
        logger.error(f"Error in rules refresh task: {e}")