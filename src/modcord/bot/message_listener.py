"""Message listener Cog for Modcord.

This cog handles all message-related Discord events (on_message, on_message_edit)
and integrates with the moderation batching system.
"""

import datetime
import discord
from discord.ext import commands

from modcord.moderation.moderation_datatypes import ModerationImage, ModerationMessage
from modcord.util.image_utils import download_image_to_pil, generate_image_hash_id

from modcord.configuration.guild_settings import guild_settings_manager
from modcord.moderation.message_batch_manager import message_batch_manager
from modcord.util.logger import get_logger
from modcord.rules_cache.rules_cache_manager import rules_cache_manager
from modcord.util import discord_utils

logger = get_logger("message_listener_cog")


class MessageListenerCog(commands.Cog):
    """Cog responsible for handling message creation and editing events."""

    def __init__(self, discord_bot_instance):
        """
        Initialize the message listener cog.

        Parameters
        ----------
        discord_bot_instance:
            The Discord bot instance to attach this cog to.
        """
        self.bot = discord_bot_instance
        self.discord_bot_instance = discord_bot_instance
        logger.info("[MESSAGE LISTENER] Message listener cog loaded")



    @staticmethod
    def _extract_embed_content(message: discord.Message) -> str:
        """Extract and format content from message embeds."""
        if not message.embeds:
            return ""
        
        embed_parts = []
        for embed in message.embeds:
            parts = []
            
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
            
            if parts:
                embed_parts.append(" ".join(parts))
        
        return "\n".join(embed_parts) if embed_parts else ""

    def _build_moderation_images(self, message: discord.Message) -> list[tuple[str, ModerationImage]]:
        """Transform Discord attachments into (url, ModerationImage) tuples for download."""
        images: list[tuple[str, ModerationImage]] = []

        for attachment in message.attachments:
            if not discord_utils.is_image_attachment(attachment):
                continue

            image_id = generate_image_hash_id(attachment.url)
            mod_image = ModerationImage(
                image_id=image_id,
                pil_image=None,
            )
            images.append((attachment.url, mod_image))

        return images

    async def _download_images_for_moderation_images(
        self,
        image_tuples: list[tuple[str, ModerationImage]]
    ) -> list[ModerationImage]:
        """Download PIL images for all ModerationImage objects.
        
        Args:
            image_tuples: List of (url, ModerationImage) tuples
            
        Returns:
            List of ModerationImage objects with pil_image set (only successful downloads)
        """
        import asyncio
        
        successful_images = []
        
        for url, img in image_tuples:
            # Run download in thread to avoid blocking
            pil_image = await asyncio.to_thread(download_image_to_pil, url)
            if pil_image:
                img.pil_image = pil_image
                successful_images.append(img)
            else:
                logger.warning(f"Failed to download image from {url}")
        
        return successful_images

    async def _create_moderation_message(
        self, 
        message: discord.Message, 
        content: str,
        include_discord_message: bool = False
    ) -> ModerationMessage:
        """
        Create a ModerationMessage from a Discord message.

        Parameters
        ----------
        message:
            The Discord message to convert.
        content:
            The cleaned message content.
        include_discord_message:
            Whether to include the Discord message reference in the payload.

        Returns
        -------
        ModerationMessage
            The normalized moderation message structure.
        """
        # Discord's created_at is already UTC-aware, just format it
        timestamp_iso = message.created_at.replace(microsecond=0).isoformat().replace('+00:00', 'Z')
        
        # Build image tuples and download PIL images immediately
        image_tuples = self._build_moderation_images(message)
        images = await self._download_images_for_moderation_images(image_tuples)
        
        return ModerationMessage(
            message_id=str(message.id),
            user_id=str(message.author.id),
            content=content,
            timestamp=timestamp_iso,
            guild_id=message.guild.id if message.guild else None,
            channel_id=message.channel.id,
            images=images,
            discord_message=message if include_discord_message else None,
        )

    def _get_message_content(self, message: discord.Message) -> str:
        """Extract combined text and embed content from a message."""
        actual_content = message.clean_content.strip()
        embed_content = self._extract_embed_content(message)
        
        if embed_content:
            return f"{actual_content}\n{embed_content}" if actual_content else embed_content
        return actual_content

    @commands.Cog.listener(name='on_message')
    async def on_message(self, message: discord.Message):
        """
        Handle new messages and queue them for moderation analysis.

        This handler:
        1. Filters out DMs, other bots, and empty messages using centralized logic
        2. Refreshes rules cache if posted in a rules channel
        3. Queues user messages for batch AI moderation (if enabled)
        """
        # Use centralized filtering logic
        bot_user_id = self.bot.user.id if self.bot.user else None
        if not discord_utils.should_process_message(message, bot_user_id=bot_user_id):
            return

        # Extract message content
        message_content = self._get_message_content(message)
        
        log_preview = message_content if message_content else "[no text]"
        if any(discord_utils.is_image_attachment(att) for att in message.attachments):
            log_preview = f"{log_preview} [images]"

        logger.debug(f"Received message from {message.author}: {log_preview[:80]}")

        # Refresh rules cache if this was posted in a rules channel
        if isinstance(message.channel, discord.abc.GuildChannel):
            await rules_cache_manager.refresh_if_rules_channel(message.channel)

        # Check if AI moderation is enabled for this guild (guaranteed non-None by should_process_message)
        assert message.guild is not None
        if not guild_settings_manager.is_ai_enabled(message.guild.id):
            logger.debug(f"AI moderation disabled for guild {message.guild.name}")
            return

        # Add message to the batching system for AI moderation
        try:
            batch_message = await self._create_moderation_message(
                message, 
                message_content, 
                include_discord_message=True
            )
            await message_batch_manager.add_message_to_batch(message.channel.id, batch_message)
            logger.debug(f"Added message to batch for channel {message.channel.id}")
        except Exception as e:
            logger.error(f"Error adding message to batch: {e}")

    @commands.Cog.listener(name='on_message_edit')
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        """
        Handle message edits by refreshing rules (if needed) and updating batches.
        """
        # Use centralized filtering logic
        bot_user_id = self.bot.user.id if self.bot.user else None
        if not discord_utils.should_process_message(after, bot_user_id=bot_user_id):
            return

        # If the content didn't change, nothing to do
        if (before.content or "").strip() == (after.content or "").strip():
            return

        # Refresh rules cache if this edit occurred in a rules channel
        if isinstance(after.channel, discord.abc.GuildChannel):
            await rules_cache_manager.refresh_if_rules_channel(after.channel)

        # Re-evaluate whether message should be part of moderation batches
        if not discord_utils.should_process_message(after, bot_user_id=bot_user_id):
            await message_batch_manager.remove_message_from_batch(after.channel.id, str(after.id))
            logger.debug(
                "Edited message %s in channel %s no longer qualifies for moderation batch",
                after.id,
                after.channel.id,
            )
            return

        try:
            message_content = self._get_message_content(after)
            updated_entry = await self._create_moderation_message(
                after,
                message_content,
                include_discord_message=True,
            )
            await message_batch_manager.update_message_in_batch(after.channel.id, updated_entry)
            logger.debug(
                "Updated moderated payload for edited message %s in channel %s",
                after.id,
                after.channel.id,
            )
        except Exception as exc:
            logger.error("[MESSAGE LISTENER] Failed to update edited message %s: %s", after.id, exc)

    @commands.Cog.listener(name='on_message_delete')
    async def on_message_delete(self, message: discord.Message):
        """Handle message deletions by pruning pending moderation payloads."""
        if message.guild is None:
            return
        
        await message_batch_manager.remove_message_from_batch(message.channel.id, str(message.id))
        logger.debug(
            "Removed deleted message %s from moderation batch for channel %s",
            message.id,
            message.channel.id,
        )


def setup(discord_bot_instance):
    """Register the MessageListenerCog with the bot."""
    discord_bot_instance.add_cog(MessageListenerCog(discord_bot_instance))