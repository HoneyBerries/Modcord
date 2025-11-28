"""
Discord history fetching and message conversion utilities.

This module handles fetching message history from Discord channels and converting
Discord message objects into ModerationMessage format for processing.
"""

from __future__ import annotations

from typing import List, Set

import discord
from modcord.configuration.app_configuration import app_config
from modcord.datatypes.discord_datatypes import UserID, MessageID, ChannelID, GuildID
from modcord.datatypes.moderation_datatypes import ModerationMessage
from modcord.util.logger import get_logger
from modcord.util import discord_utils

logger = get_logger("discord_history_fetcher")


class DiscordHistoryFetcher:
    """
    Fetches and converts Discord message history for moderation context.
    
    This class provides utilities to:
    - Fetch recent message history from Discord channels
    - Convert Discord messages to ModerationMessage format
    - Extract embed content from messages
    - Filter bot messages and duplicates
    - Respect configured history limits and lookback windows
    
    Args:
        bot_instance (discord.Bot): The Discord bot instance for API access.
    """

    def __init__(self, bot_instance: discord.Bot) -> None:
        """
        Initialize the history fetcher.

        Args:
            bot_instance (discord.Bot): The Discord bot instance for API access.

        Returns:
            None
        """
        self._bot = bot_instance

    async def fetch_history_context(
        self,
        channel_id: ChannelID,
        exclude_message_ids: Set[MessageID],
        history_limit: int = 100,
    ) -> List[ModerationMessage]:
        """
        Fetch recent message history from a Discord channel for moderation context.
        
        Uses adaptive paging to efficiently fetch exactly the required number of
        usable messages. Automatically filters out bot messages and excludes messages
        already in the current batch.
        
        Args:
            channel_id (ChannelID | int): The Discord channel ID to fetch history from.
            exclude_message_ids (Set[MessageID]): Set of message IDs to skip (current batch messages).
            history_limit (int | None): Maximum number of historical messages to fetch.
                If None, uses the value from ai_settings.history_context_messages.
        
        Returns:
            List[ModerationMessage]: List of converted historical messages in chronological
                order (oldest first), up to the specified limit.
        
        Note:
            Only fetches from text channels and threads. Bot messages are automatically excluded.
        """
        channel_id_int = ChannelID(channel_id).to_int()
        exclude_ids_set = set(exclude_message_ids)

        channel = self._bot.get_channel(channel_id_int)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            logger.debug("[HISTORY FETCHER] Channel %s is not a text channel or thread", channel_id)
            return []

        if history_limit is None:
            try:
                history_limit = app_config.ai_settings.history_context_messages
            except Exception:
                history_limit = 20

        results: List[ModerationMessage] = []
        results_count = 0
        last_message = None  # Used for pagination

        try:
            while results_count < history_limit:
                # Always fetch the maximum allowed (100) to minimize API calls
                history = channel.history(
                    limit=100,
                    before=last_message  # paginate backward
                )

                batch_empty = True

                async for discord_msg in history:
                    batch_empty = False
                    last_message = discord_msg  # update pagination cursor

                    msg_id = MessageID.from_message(discord_msg)
                    if msg_id in exclude_ids_set:
                        continue
                    
                    if not discord_utils.should_process_message(discord_msg):
                        continue

                    mod_msg = self.convert_discord_message(discord_msg)
                    if mod_msg:
                        results.append(mod_msg)
                        results_count += 1
                        if results_count >= history_limit:
                            break

                if batch_empty:
                    # No more messages available in history
                    break

        except discord.Forbidden:
            logger.warning("[HISTORY FETCHER] Missing permissions to read history for channel %s", channel_id)
        except discord.NotFound:
            logger.warning("[HISTORY FETCHER] Channel %s not found while fetching history", channel_id)
        except Exception as exc:
            logger.error("[HISTORY FETCHER] Unexpected error fetching history for channel %s: %s", channel_id, exc)

        return results


    def convert_discord_message(self, message: discord.Message) -> ModerationMessage | None:
        """
        Convert a Discord message to ModerationMessage format for processing.
        
        Extracts text content from the Discord message and packages it into the
        normalized ModerationMessage format. Images are not included for historical
        context to avoid performance and cost issues.
        
        Args:
            message (discord.Message): Discord message object to convert.
        
        Returns:
            ModerationMessage | None: Converted message with text content, or None
                if the message has no text content.
        """
        content = (message.clean_content or "").strip()

        # Only include messages with text content (no images for history)
        if not content:
            return None
        
        # Make sure stuff aren't null
        if message.guild is None or message.channel is None:
            return None

        return ModerationMessage(
            message_id=MessageID.from_message(message),
            user_id=UserID.from_user(message.author),
            content=content,
            timestamp=message.created_at,
            guild_id=GuildID.from_guild(message.guild),
            channel_id=ChannelID.from_channel(message.channel),
            images=[],
        )
