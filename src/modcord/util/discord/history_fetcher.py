from typing import Set, List

import discord

from modcord.datatypes.discord_datatypes import ChannelID, MessageID, UserID, GuildID
from modcord.datatypes.moderation_datatypes import ModerationMessage
from modcord.util import logger
from modcord.util.discord import discord_utils

logger = logger.get_logger("history_fetcher")

async def fetch_history_context(
    bot,
    channel_id: ChannelID,
    exclude_message_ids: Set[MessageID],
    history_limit: int,
) -> List[ModerationMessage]:
    channel = bot.get_channel(int(channel_id))
    if not isinstance(channel, discord.TextChannel | discord.Thread | discord.VoiceChannel):
        logger.debug("Channel %s is not text/thread", channel_id)
        return []

    exclude_ids = set(exclude_message_ids)
    results: List[ModerationMessage] = []

    try:
        async for msg in channel.history(limit=history_limit):
            if (
                MessageID.from_message(msg) in exclude_ids
                or not discord_utils.should_process_message(msg)
                or not msg.clean_content.strip()
            ):
                continue

            results.append(
                ModerationMessage(
                    message_id=MessageID.from_message(msg),
                    user_id=UserID.from_user(msg.author),
                    content=msg.clean_content.strip(),
                    timestamp=msg.created_at,
                    guild_id=GuildID.from_guild(msg.guild),
                    channel_id=ChannelID.from_channel(msg.channel),
                    images=(),
                )
            )
            if len(results) >= history_limit:
                break

    except discord.Forbidden:
        logger.warning("Missing permissions for channel %s", channel_id)
    except discord.NotFound:
        logger.warning("Channel %s not found", channel_id)
    except Exception:
        logger.exception("Unexpected error fetching history for %s", channel_id)

    results.reverse()
    return results
