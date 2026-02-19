"""Shared helpers for collecting content from Discord channels.

Provides utilities for:
- Extracting messages and embeds from channels
- Gathering server rules from rule-like channels
- Extracting channel-specific guidelines from channel topics
"""

from __future__ import annotations

import re
from typing import List

import discord

from modcord.util.discord import discord_utils
from modcord.util.logger import get_logger

logger = get_logger("collector")


RULE_CHANNEL_PATTERN = re.compile(
    r"^(?:(?!moderation[_-]?only).)*(rules?|guidelines?|regulations?|policy|policies|"
    r"code[-_ ]?of[-_ ]?conduct|server[-_ ]?(rules?|guidelines?)|mod[-_ ]?(rules?|guidelines?)|"
    r"law|expectations?|standards?)",
    re.IGNORECASE,
)
"""Heuristic regex to identify channels likely containing server rules."""


def is_rules_channel(channel: discord.abc.GuildChannel) -> bool:
    """Return True if channel name matches the rules pattern."""
    return bool(channel.name and RULE_CHANNEL_PATTERN.search(channel.name))


async def collect_messages(channel: discord.TextChannel) -> List[str]:
    """
    Collect all message content and embed text from a channel.

    Args:
        channel: The text channel to read.

    Returns:
        List of non-empty text strings (message content + embed text).
    """
    texts: List[str] = []
    try:
        async for msg in channel.history(oldest_first=True):
            if msg.content and (text := msg.content.strip()):
                texts.append(text)
            for embed in msg.embeds:
                texts.extend(discord_utils.extract_embed_text_from_message(embed))
    except discord.Forbidden:
        logger.warning("No permission to read channel: %s", channel.name)
    except Exception as exc:
        logger.warning("Error reading channel %s: %s", channel.name, exc)
    return texts


async def collect_rules(guild: discord.Guild) -> str:
    """
    Gather rules text from all rule-like channels in a guild.

    Args:
        guild: The guild to scan.

    Returns:
        Concatenated rules text, or empty string if none found.
    """
    all_texts: List[str] = []
    for ch in guild.text_channels:
        if is_rules_channel(ch):
            all_texts.extend(await collect_messages(ch))
    if all_texts:
        logger.info("Collected %d rule segments from guild %s", len(all_texts), guild.name)
    return "\n\n".join(all_texts)


def collect_channel_topic(channel: discord.TextChannel) -> str:
    """
    Extract channel-specific guidelines from the channel topic.

    Args:
        channel: The text channel.

    Returns:
        The trimmed topic string, or empty string if not set.
    """
    if channel.topic and (text := channel.topic.strip()):
        return text
    return ""