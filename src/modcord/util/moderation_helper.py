


"""Moderation helper functions used by the event listener.

These helpers implement batching, rules-refresh, and action application
logic. They are free functions that accept the cog instance as the
first parameter (``self``).
"""

import asyncio

import discord

from modcord.ai.ai_core import moderation_processor
from modcord.configuration.guild_settings import guild_settings_manager
from modcord.bot import rules_manager
from modcord.util.moderation_models import ActionData, ActionType, ModerationBatch, ModerationMessage
from modcord.util import discord_utils
from modcord.util.logger import get_logger

logger = get_logger("moderation_helper")


async def process_message_batch(self, batch: ModerationBatch) -> None:
    """Process a batch of messages.

    Runs the AI moderation pipeline for the provided batch and applies
    any resulting actions.
    """
    channel_id = batch.channel_id
    try:
        if batch.is_empty():
            logger.debug(f"Empty batch for channel {batch.channel_id}, skipping")
            return
        logger.info(f"Processing batch of {len(batch.messages)} messages for channel {batch.channel_id}")

        messages = batch.messages
        channel_id = batch.channel_id

        # Get guild info from the first message for server rules
        guild_id = messages[0].guild_id
        server_rules = guild_settings_manager.get_server_rules(guild_id) if guild_id else ""

        # Check if AI moderation is enabled for this guild
        if guild_id and not guild_settings_manager.is_ai_enabled(guild_id):
            logger.debug(f"AI moderation disabled for guild {guild_id}, skipping batch")
            return

        # Process the batch with AI
        actions = await moderation_processor.get_batch_moderation_actions(
            batch=batch,
            server_rules=server_rules,
        )

        logger.info(f"AI returned {len(actions)} actions for channel {channel_id}")

        # Apply each action
        for action_data in actions:
            try:
                await apply_batch_action(self, action_data, batch)
            except Exception as e:
                logger.error(f"Error applying action {action_data} in channel {channel_id}: {e}")

    except Exception as e:
        logger.error(f"Error processing message batch for channel {channel_id}: {e}")



async def apply_batch_action(self, action: ActionData, batch: ModerationBatch) -> bool:
    """Execute a single moderation action produced by the AI.

    Finds a suitable pivot message, performs the action (ban/kick/timeout/etc.),
    and returns True on success or False on failure.
    """
    try:
        if action.action is ActionType.NULL or not action.user_id:
            return False

        user_messages = [msg for msg in batch.messages if msg.user_id == action.user_id]
        if not user_messages:
            logger.warning(f"No messages found for user {action.user_id} in batch for channel {batch.channel_id}")
            return False

        # Use the most recent message that still has the Discord message object reference
        pivot_entry: ModerationMessage | None = None
        for candidate in reversed(user_messages):
            if candidate.discord_message is not None:
                pivot_entry = candidate
                break
        if not pivot_entry:
            logger.warning(f"No Discord message object found for user {action.user_id}")
            return False

        logger.info(
            f"Applying {action.action.value} action to user {action.user_id} in channel {batch.channel_id}: {action.reason}"
        )

        return await discord_utils.apply_action_decision(
            action=action,
            pivot=pivot_entry,
            bot_user=self.bot.user,
            bot_client=self.bot,
        )

    except Exception as e:
        logger.error(f"Error applying batch action {action.to_wire_dict()}: {e}")
        return False


async def refresh_rules_cache_if_rules_channel(self, channel: discord.abc.Messageable) -> None:
    """Refresh the rules cache when activity occurs in a rules channel.

    No-op when the channel does not match the rules-channel heuristics.
    """
    if isinstance(channel, discord.TextChannel) and isinstance(channel.name, str) and rules_manager.RULE_CHANNEL_PATTERN.search(channel.name):
        guild = channel.guild
        if guild is None:
            return
        try:
            await rules_manager.refresh_guild_rules(guild, settings=guild_settings_manager)
            logger.info(f"Rules cache refreshed immediately due to activity in rules channel: {channel.name}")
        except Exception as e:
            logger.error(f"Failed to refresh rules cache for channel {channel}: {e}")


async def refresh_rules_cache_task(self):
    """Background task that continuously refreshes the rules cache.

    Intended to be started with ``asyncio.create_task(...)`` and will run
    until cancelled.
    """
    try:
        await rules_manager.run_periodic_refresh(self.bot, settings=guild_settings_manager)
    except asyncio.CancelledError:
        logger.info("Rules cache refresh task cancelled")
        raise
    except Exception as e:
        logger.error(f"Error in rules cache refresh task: {e}")