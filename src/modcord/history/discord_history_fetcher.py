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

logger = get_logger("discord_history_fetcher")

# Discord attachment types considered images for moderation context
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")


class DiscordHistoryFetcher:
    """
    Fetches and converts Discord message history for moderation processing.
    
    This class provides utilities to:
    - Fetch recent message history from Discord channels
    - Convert Discord messages to ModerationMessage format
    - Extract embed content and images from messages
    - Filter bot messages and duplicates
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
        Fetch recent message history from a Discord channel.

        Args:
            channel_id (int): Discord channel ID to fetch history from.
            exclude_message_ids (Set[str]): Message IDs to exclude (e.g., current batch messages).
            history_limit (int | None): Maximum number of history messages to return. 
                If None, uses config value from 'history_context_messages' (default 20).

        Returns:
            List[ModerationMessage]: List of historical messages in ModerationMessage format.
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

        # Fetch more than needed to account for bot messages and exclusions
        fetch_count = min(history_limit * 2, 100)
        results: List[ModerationMessage] = []
        results_count = 0  # Track count separately to avoid repeated len() calls

        try:
            async for discord_msg in channel.history(limit=fetch_count):
                # Use string ID directly - avoid creating new string for comparison
                msg_id_str = str(discord_msg.id)
                if msg_id_str in exclude_message_ids:
                    continue
                if discord_msg.author.bot:
                    continue

                mod_msg = self.convert_discord_message(discord_msg)
                if mod_msg:
                    results.append(mod_msg)
                    results_count += 1
                    if results_count >= history_limit:
                        break
        except discord.Forbidden:
            logger.warning("Missing permissions to read history for channel %s", channel_id)
        except discord.NotFound:
            logger.warning("Channel %s not found while fetching history", channel_id)
        except Exception as exc:
            logger.error(
                "Unexpected error fetching history for channel %s: %s",
                channel_id,
                exc,
            )

        return results

    def convert_discord_message(self, message: discord.Message) -> ModerationMessage | None:
        """
        Convert a Discord message to ModerationMessage format.

        Args:
            message (discord.Message): Discord message object to convert.

        Returns:
            ModerationMessage | None: Converted message, or None if message has no content/images.
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
            discord_message=None,
        )

    @staticmethod
    def _extract_embed_content(message: discord.Message) -> str:
        """
        Extract text content from message embeds.

        Args:
            message (discord.Message): Discord message with potential embeds.

        Returns:
            str: Concatenated embed content as formatted text.
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
        Extract image attachments from a Discord message.

        Args:
            message (discord.Message): Discord message with potential attachments.

        Returns:
            List[ModerationImage]: List of moderation image objects.
        """
        images: List[ModerationImage] = []
        for attachment in message.attachments:
            if not self._is_image_attachment(attachment):
                continue
            images.append(
                ModerationImage(
                    image_id=generate_image_hash_id(attachment.url),
                    pil_image=None,
                )
            )
        return images

    @staticmethod
    def _is_image_attachment(attachment: discord.Attachment) -> bool:
        """
        Determine if a Discord attachment is an image.

        Args:
            attachment (discord.Attachment): Attachment to check.

        Returns:
            bool: True if attachment is an image, False otherwise.
        """
        content_type = (attachment.content_type or "").lower()
        if content_type.startswith("image/"):
            return True
        if attachment.width is not None and attachment.height is not None:
            return True
        filename = (attachment.filename or "").lower()
        return filename.endswith(IMAGE_EXTENSIONS)
