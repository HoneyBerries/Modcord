"""Moderation helper functions used by the event listener.

These helpers implement batching, rules-refresh, and action application
logic. They are free functions that accept the cog instance as the
first parameter (``self``).
"""

import asyncio

import discord

from modcord.ai.ai_moderation_processor import model_state, moderation_processor
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

    Parameters
    ----------
    batch:
        Group of channel messages accumulated for moderation review.
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

        if not model_state.available:
            logger.debug(
                "Skipping batch for channel %s; AI model unavailable (%s)",
                batch.channel_id,
                model_state.init_error or "not initialized",
            )
            return

        # Process the batch with AI
        actions = await moderation_processor.get_batch_moderation_actions(
            batch=batch,
            server_rules=server_rules,
        )

        logger.info(f"AI returned {len(actions)} actions for channel {channel_id}")

        # Build lookup for message IDs per user to guard against cross-batch actions
        message_ids_by_user: dict[str, set[str]] = {}
        for message in messages:
            user_key = str(message.user_id)
            message_ids_by_user.setdefault(user_key, set()).add(str(message.message_id))

        # Apply each action
        for action_data in actions:
            allowed_ids = message_ids_by_user.get(action_data.user_id, set())
            if action_data.message_ids:
                filtered_ids = [mid for mid in action_data.message_ids if mid in allowed_ids]
                if len(filtered_ids) != len(action_data.message_ids):
                    logger.warning(
                        "Filtered out %d message ids not present in batch for user %s",
                        len(action_data.message_ids) - len(filtered_ids),
                        action_data.user_id,
                    )
                action_data.replace_message_ids(filtered_ids)
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

    Parameters
    ----------
    action:
        The moderation action to apply.
    batch:
        The batch that produced the action, used for context and logging.

    Returns
    -------
    bool
        ``True`` when the action was executed successfully.
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

        guild_id = pivot_entry.guild_id
        if guild_id is not None and not guild_settings_manager.is_action_allowed(guild_id, action.action):
            logger.info(
                "Skipping %s for guild %s: disabled in guild settings",
                action.action.value,
                guild_id,
            )
            return False

        logger.debug(
            f"Applying {action.action.value} action to user {action.user_id} in channel {batch.channel_id}: {action.reason}"
        )

        discord_message = pivot_entry.discord_message
        if not isinstance(discord_message, discord.Message):
            logger.warning("Pivot message missing Discord message instance for user %s", action.user_id)
            return False

        guild = discord_message.guild
        author = discord_message.author
        if guild is None or not isinstance(author, discord.Member):
            logger.debug("Cannot apply action %s; missing guild/member context", action.action.value)
            return False

        if guild.owner_id == author.id:
            logger.info("Skipping %s; target is guild owner", action.action.value)
            return False

        if discord_utils.has_elevated_permissions(author):
            logger.info("Skipping %s; target has elevated permissions", action.action.value)
            return False

        bot_member = guild.me
        if bot_member and author.top_role >= bot_member.top_role:
            logger.info(
                "Skipping %s for %s; target role is higher or equal to bot role",
                action.action.value,
                author.id,
            )
            return False

        bot_perms = bot_member.guild_permissions if bot_member else None
        if action.action is ActionType.BAN and (not bot_perms or not bot_perms.ban_members):
            logger.warning("Cannot ban user %s; bot lacks ban_members permission", author.id)
            return False
        if action.action is ActionType.KICK and (not bot_perms or not bot_perms.kick_members):
            logger.warning("Cannot kick user %s; bot lacks kick_members permission", author.id)
            return False
        if action.action is ActionType.TIMEOUT and (not bot_perms or not getattr(bot_perms, "moderate_members", False)):
            logger.warning("Cannot timeout user %s; bot lacks moderate_members permission", author.id)
            return False
        if action.action is ActionType.DELETE:
            channel_obj = discord_message.channel
            base_channel: discord.TextChannel | None = None
            if isinstance(channel_obj, discord.TextChannel):
                base_channel = channel_obj
            elif isinstance(channel_obj, discord.Thread) and isinstance(channel_obj.parent, discord.TextChannel):
                base_channel = channel_obj.parent

            if base_channel is None:
                logger.warning("Cannot delete messages in unsupported channel type %s", type(channel_obj).__name__)
                return False

            if not discord_utils.bot_can_manage_messages(base_channel, guild):
                logger.warning("Cannot delete messages in channel %s; missing manage_messages", base_channel.id)
                return False

        return await discord_utils.apply_action_decision(
            action=action,
            pivot=pivot_entry,
            bot_user=self.bot.user,
            bot_client=self.bot,
        )

    except Exception as e:
        logger.warning(f"Error applying batch action {action.to_wire_dict()}: {e}")
        return False


async def refresh_rules_cache_if_rules_channel(self, channel: discord.abc.Messageable) -> None:
    """Refresh the rules cache when activity occurs in a rules channel.

    No-op when the channel does not match the rules-channel heuristics.

    Parameters
    ----------
    channel:
        Channel that triggered an event and may require a rules refresh.
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
    """Background task that periodically refreshes the cached server rules."""
    try:
        await rules_manager.run_periodic_refresh(self.bot, settings=guild_settings_manager)
    except asyncio.CancelledError:
        logger.info("Rules cache refresh task cancelled")
        raise
    except Exception as e:
        logger.error(f"Error in rules cache refresh task: {e}")