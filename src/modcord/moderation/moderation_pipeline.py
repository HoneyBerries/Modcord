"""
Moderation pipeline for server-wide AI moderation.

This module orchestrates the full moderation flow:
- Validates the server batch (non-empty, AI enabled)
- Gets AI moderation decisions via LLMEngine (single request per guild)
- Routes actions to Discord (delete, timeout, kick, ban)

Features:
- Single ServerModerationBatch per guild per batch interval
- Server-wide AI inference (all channels in one request)
- Applies moderation actions back to Discord contexts
"""

import discord
from openai import api_key

from modcord.ai.llm_engine import LLMEngine
from modcord.datatypes.action_datatypes import ActionData, ActionType
from modcord.datatypes.discord_datatypes import GuildID
from modcord.datatypes.guild_settings import GuildSettings
from modcord.datatypes.moderation_datatypes import ServerModerationBatch
from modcord.moderation import moderation_helper
from modcord.settings.guild_settings_manager import guild_settings_manager
from modcord.util.discord import discord_utils
from modcord.util.logger import get_logger

logger = get_logger("moderation_engine")

class ModerationPipeline:
    """
    Engine for processing server-wide moderation batches through the AI pipeline.
    
    This class owns the batch processing logic and coordinates between
    the AI moderation processor and Discord action execution.
    
    Attributes:
        bot: The Discord bot instance for API access.
        api_key: The OpenAI-compatible API key.
        api_url: The OpenAI-compatible API base URL.
    """
    
    def __init__(self, bot: discord.Bot, openai_api_key: str, api_url: str) -> None:
        """
        Initialize the moderation engine.
        
        Args:
            bot: Discord bot instance for API access and guild lookups.
            openai_api_key: The OpenAI-compatible API key.
            api_url: The OpenAI-compatible API base URL.
        """
        self._bot = bot
        self._llm_engine = LLMEngine(api_key=openai_api_key, base_url=api_url)
    
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
        3. Apply actions (delete, timeout, kick, ban)
        
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
        actions = await self._llm_engine.get_moderation_actions(batch)

        if not actions:
            logger.debug("[PIPELINE] No actions returned for guild %s", batch.guild_id)
            return

        # Apply actions
        for action in actions:
            if action.action is ActionType.NULL:
                continue
            await self._apply_batch_action(action, batch, settings)

    async def _apply_batch_action(
        self,
        action_data: ActionData,
        batch: ServerModerationBatch,
        settings: GuildSettings | None = None,
    ) -> bool:
        """
        Apply a moderation action to a user in the batch.
        
        Args:
            action_data: ActionData containing action type and parameters.
            batch: Server batch containing the target user.
            settings: Guild settings for notification channel resolution.
        
        Returns:
            True if action was successfully applied, False otherwise.
        """
        logger.debug(
            "[PIPELINE] Applying action %s for user %s in guild %s",
            action_data.action.value,
            action_data.user_id,
            batch.guild_id
        )
        
        if action_data.action is ActionType.NULL or not action_data.user_id:
            logger.debug("[PIPELINE] Skipping: action is NULL or no user_id")
            return False

        # Find target user with Discord context
        target_user = moderation_helper.find_target_user_in_batch(batch, action_data.user_id)
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

        if not await guild_settings_manager.is_action_allowed(guild_id, action_data.action):
            logger.debug(
                "[PIPELINE] Action %s not allowed in guild %s",
                action_data.action.name,
                guild_id
            )
            return False

        if guild.owner_id == member.id or discord_utils.has_elevated_permissions(member):
            logger.debug(
                "[PIPELINE] Skipping action for user %s: elevated permissions",
                action_data.user_id
            )
            return False

        try:
            # Derive notification channel (mod-log > user channel > batch fallback)
            notification_channel = _resolve_notification_channel(guild, settings)
            
            result = await moderation_helper.apply_action(
                action=action_data,
                member=member,
                bot=self._bot,
                notification_channel=notification_channel,
            )
            
            logger.debug(
                "[PIPELINE] Applied action %s for user %s: %s",
                action_data.action.value,
                action_data.user_id,
                result
            )
            return result
        
        except discord.Forbidden:
            logger.warning(
                "Permission error applying action %s for user %s",
                action_data.action.value,
                action_data.user_id
            )
            return False
        
        except Exception as e:
            logger.error(
                "Error applying action %s for user %s: %s",
                action_data.action.value,
                action_data.user_id,
                e,
                exc_info=True)
            return False


def _resolve_notification_channel(guild: discord.Guild, settings: GuildSettings) -> discord.TextChannel | None:
    """Derive the best channel to post a notification embed in.

    Priority:
    1. Configured mod-log channel (``settings.mod_log_channel_id``)
    2. Default system channel set for the guild

    Args:
        guild: Discord guild object.
        settings: Optional guild settings for mod-log channel.

    Returns:
        A TextChannel if one can be resolved, otherwise None.
    """
    # 1. Configured mod-log channel
    if settings and settings.mod_log_channel_id:
        ch = guild.get_channel(int(settings.mod_log_channel_id))
        if isinstance(ch, discord.TextChannel):
            return ch

    # 2. Just use the default system channel
    return guild.system_channel
