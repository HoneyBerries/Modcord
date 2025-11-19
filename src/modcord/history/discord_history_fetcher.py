"""
Discord history fetching and message conversion utilities.

This module handles fetching message history from Discord channels and converting
Discord message objects into ModerationMessage format for processing.
"""

from __future__ import annotations

import datetime
from typing import List, Set

import discord

from modcord.configuration.app_configuration import app_config
from modcord.moderation.moderation_datatypes import ModerationImage, ModerationMessage
from modcord.util.image_utils import generate_image_hash_id
from modcord.util.logger import get_logger
from modcord.util import discord_utils

logger = get_logger("discord_history_fetcher")

# Discord attachment types considered images for moderation context
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")


class DiscordHistoryFetcher:
    """
    Fetches and converts Discord message history for moderation context.
    
    This class provides utilities to:
    - Fetch recent message history from Discord channels
    - Convert Discord messages to ModerationMessage format
    - Extract embed content and images from messages
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
    channel_id: int,
    exclude_message_ids: Set[str],
    history_limit: int | None = None,
    ) -> List[ModerationMessage]:
        """
        Fetch recent message history from a Discord channel for moderation context.
        
        Uses adaptive paging to efficiently fetch exactly the required number of
        usable messages. Automatically filters out bot messages and excludes messages
        already in the current batch.
        
        Args:
            channel_id (int): The Discord channel ID to fetch history from.
            exclude_message_ids (Set[str]): Set of message IDs to skip (current batch messages).
            history_limit (int | None): Maximum number of historical messages to fetch.
                If None, uses the value from ai_settings.history_context_messages.
        
        Returns:
            List[ModerationMessage]: List of converted historical messages in chronological
                order (oldest first), up to the specified limit.
        
        Note:
            Only fetches from text channels and threads. Bot messages are automatically excluded.
        """

        channel = self._bot.get_channel(channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            logger.debug("Channel %s is not a text channel or thread", channel_id)
            return []

        if history_limit is None:
            try:
                history_limit = int(app_config.ai_settings.get("history_context_messages", 20))
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

                    msg_id_str = str(discord_msg.id)
                    if msg_id_str in exclude_message_ids:
                        continue
                    
                    if not discord_utils.should_process_message(discord_msg, bot_user_id=self._bot.user.id if self._bot.user else None):
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
            logger.warning("Missing permissions to read history for channel %s", channel_id)
        except discord.NotFound:
            logger.warning("Channel %s not found while fetching history", channel_id)
        except Exception as exc:
            logger.error("Unexpected error fetching history for channel %s: %s", channel_id, exc)

        return results


    def convert_discord_message(self, message: discord.Message) -> ModerationMessage | None:
        """
        Convert a Discord message to ModerationMessage format for processing.
        
        Extracts text content, embed content, and image attachments from the Discord
        message and packages them into the normalized ModerationMessage format.
        
        Args:
            message (discord.Message): Discord message object to convert.
        
        Returns:
            ModerationMessage | None: Converted message with all relevant data, or None
                if the message has no content and no images.
        """
        content = (message.clean_content or "").strip()
        embed_content = self._extract_embed_content(message)
        if embed_content:
            content = f"{content}\n{embed_content}" if content else embed_content

        images = self._build_moderation_images(message)

        if not content and not images:
            return None

        created_at = message.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=datetime.timezone.utc)

        return ModerationMessage(
            message_id=str(message.id),
            user_id=str(message.author.id),
            content=content,
            timestamp=created_at.astimezone(datetime.timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            guild_id=message.guild.id if message.guild else None,
            channel_id=message.channel.id if message.channel else None,
            images=images,
            discord_message=message,
        )

    @staticmethod
    def _extract_embed_content(message: discord.Message) -> str:
        """
        Extract all text content from message embeds.
        
        Extracts and formats text from embed titles, descriptions, fields,
        footers, and author names into a single concatenated string.
        
        Args:
            message (discord.Message): Discord message with potential embeds.
        
        Returns:
            str: Concatenated embed content as formatted text, or empty string if no embeds.
        """
        if not message.embeds:
            return ""

        parts: List[str] = []
        for embed in message.embeds:
            if embed.title:
                parts.append(f"[Embed Title: {embed.title}]")
            if embed.description:
                parts.append(f"[Embed Description: {embed.description}]")
            if embed.fields:
                for field in embed.fields:
                    if field.name or field.value:
                        parts.append(f"[Embed Field - {field.name}: {field.value}]")
            if embed.footer and embed.footer.text:
                parts.append(f"[Embed Footer: {embed.footer.text}]")
            if embed.author and embed.author.name:
                parts.append(f"[Embed Author: {embed.author.name}]")

        return "\n".join(parts)

    def _build_moderation_images(self, message: discord.Message) -> List[ModerationImage]:
        """
        Extract image attachments from a Discord message and create ModerationImage objects.
        
        Identifies image attachments by content type, dimensions, or file extension
        and creates ModerationImage objects with hash IDs. PIL images are not loaded
        at this stage.
        
        Args:
            message (discord.Message): Discord message with potential image attachments.
        
        Returns:
            List[ModerationImage]: List of ModerationImage objects (without loaded PIL images).
        """
        images: List[ModerationImage] = []
        for attachment in message.attachments:
            if not discord_utils.is_image_attachment(attachment):
                continue
            images.append(
                ModerationImage(
                    image_id=generate_image_hash_id(attachment.url),
                    pil_image=None,
                )
            )
        return images