"""
Discord history fetching and message conversion utilities.

This module is a pure utility — it has no knowledge of Cogs, services, or
pipelines. It only knows how to fetch raw channel history and convert
discord.Message objects into the normalised ModerationMessage format.
"""

from __future__ import annotations

from typing import List, Set

import discord

from modcord.configuration.app_configuration import app_config
from modcord.datatypes.discord_datatypes import ChannelID, GuildID, MessageID, UserID
from modcord.datatypes.moderation_datatypes import ModerationMessage
from modcord.util.discord import discord_utils
from modcord.util.logger import get_logger

logger = get_logger("discord_history_fetcher")


class DiscordHistoryFetcher:
    """
    Fetches and converts Discord message history for moderation context.

    Responsibilities
    ----------------
    * Fetch recent messages from a Discord text channel or thread.
    * Skip bot messages, DMs, and messages already in the current batch.
    * Convert discord.Message objects to ModerationMessage format.
    * Images are intentionally excluded from history to keep costs low.

    Parameters
    ----------
    bot:
        The Discord bot instance used for channel lookups.
    """

    def __init__(self, bot: discord.Bot) -> None:
        self._bot = bot

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_history_context(
        self,
        channel_id: ChannelID,
        exclude_message_ids: Set[MessageID],
        history_limit: int | None = None,
    ) -> List[ModerationMessage]:
        """
        Fetch up to *history_limit* recent messages from the given channel,
        excluding any IDs in *exclude_message_ids*.

        Returns messages in chronological order (oldest first).
        """
        channel = self._bot.get_channel(channel_id.to_int())
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            logger.debug("Channel %s is not a text channel or thread — skipping history", channel_id)
            return []

        limit = history_limit or getattr(app_config, "history_context_messages", 8)
        exclude_ids = set(exclude_message_ids)
        results: List[ModerationMessage] = []

        try:
            async for raw_msg in channel.history(limit=None):
                if MessageID.from_message(raw_msg) in exclude_ids:
                    continue
                if not discord_utils.should_process_message(raw_msg):
                    continue

                converted = self._convert_message(raw_msg)
                if converted is not None:
                    results.append(converted)
                    if len(results) >= limit:
                        break

        except discord.Forbidden:
            logger.warning("Missing permissions to read history for channel %s", channel_id)
        except discord.NotFound:
            logger.warning("Channel %s not found while fetching history", channel_id)
        except Exception:
            logger.exception("Unexpected error fetching history for channel %s", channel_id)

        results.reverse()  # return chronological order (oldest first)
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _convert_message(self, message: discord.Message) -> ModerationMessage | None:
        """
        Convert a discord.Message to ModerationMessage.

        Images are omitted for history context to avoid unnecessary cost.
        Returns None when the message has no text content.
        """
        content = (message.clean_content or "").strip()
        if not content:
            return None
        if message.guild is None or message.channel is None:
            return None

        return ModerationMessage(
            message_id=MessageID.from_message(message),
            user_id=UserID.from_user(message.author),
            content=content,
            timestamp=message.created_at,
            guild_id=GuildID.from_guild(message.guild),
            channel_id=ChannelID.from_channel(message.channel),
            images=(),  # no images for historical context
        )
