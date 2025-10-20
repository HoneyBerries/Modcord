"""Message listener Cog for Modcord.

This cog handles all message-related Discord events (on_message, on_message_edit)
and integrates with the moderation batching system.
"""

import datetime
import discord
from discord.ext import commands

from modcord.util.moderation_datatypes import ModerationImage, ModerationMessage

from modcord.configuration.guild_settings import guild_settings_manager
from modcord.util.logger import get_logger
from modcord.bot import rules_manager
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
        logger.info("Message listener cog loaded")

    @staticmethod
    def _is_image_attachment(attachment: discord.Attachment) -> bool:
        """Return True if the Discord attachment should be treated as an image."""

        content_type = (attachment.content_type or "").lower()
        if content_type.startswith("image/"):
            return True

        if attachment.width is not None and attachment.height is not None:
            return True

        filename = (attachment.filename or "").lower()
        return filename.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"))

    def _build_moderation_images(self, message: discord.Message) -> list[ModerationImage]:
        """Transform Discord attachments into ModerationImage entries."""

        images: list[ModerationImage] = []
        image_index = 0
        author_id = str(message.author.id) if message.author else ""

        for attachment in message.attachments:
            if not self._is_image_attachment(attachment):
                continue

            attachment_id = str(attachment.id or f"{message.id}:{image_index}")
            images.append(
                ModerationImage(
                    attachment_id=attachment_id,
                    message_id=str(message.id),
                    user_id=author_id,
                    index=image_index,
                    filename=attachment.filename,
                    source_url=attachment.url,
                )
            )
            image_index += 1

        return images

    def _create_moderation_message(
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
        timestamp_iso = message.created_at.astimezone(
            datetime.timezone.utc
        ).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
        
        return ModerationMessage(
            message_id=str(message.id),
            user_id=str(message.author.id),
            username=str(message.author),
            content=content,
            timestamp=timestamp_iso,
            guild_id=message.guild.id if message.guild else None,
            channel_id=message.channel.id,
            images=self._build_moderation_images(message),
            discord_message=message if include_discord_message else None,
        )

    async def _should_process_message(self, message: discord.Message) -> tuple[bool, str | None]:
        """
        Check if a message should be processed for moderation.

        Parameters
        ----------
        message:
            The Discord message to check.

        Returns
        -------
        tuple[bool, str | None]
            A tuple of (should_process, cleaned_content).
            If should_process is False, cleaned_content will be None.
        """
        # Ignore DMs
        if message.guild is None:
            return False, None

        # Ignore messages from bots
        if discord_utils.is_ignored_author(message.author):
            logger.debug(f"Ignoring message from {message.author} (bot)")
            return False, None

        actual_content = message.clean_content.strip()
        has_image_attachments = any(
            self._is_image_attachment(attachment) for attachment in message.attachments
        )

        # Skip messages that lack both textual content and image attachments
        if not actual_content and not has_image_attachments:
            return False, None

        return True, actual_content if actual_content else ""

    @commands.Cog.listener(name='on_message')
    async def on_message(self, message: discord.Message):
        """
        Handle new messages: store in history and queue for AI moderation.

        This handler:
        1. Filters out DMs, bots, admins, and empty messages
        2. Refreshes rules cache if posted in a rules channel
        3. Stores message in channel history
        4. Queues message for batch AI moderation (if enabled)

        Parameters
        ----------
        message:
            The Discord message that was created.
        """
        should_process, actual_content = await self._should_process_message(message)
        if not should_process or actual_content is None:
            return

        log_preview = actual_content if actual_content else "[no text]"
        if any(self._is_image_attachment(att) for att in message.attachments):
            log_preview = f"{log_preview} [images]"

        logger.debug(f"Received message from {message.author}: {log_preview[:80]}")

        # Refresh rules cache if this was posted in a rules channel
        if isinstance(message.channel, discord.abc.GuildChannel):
            await rules_manager.refresh_rules_if_channel(message.channel)

        # Create and store message in history
        history_entry = self._create_moderation_message(message, actual_content)
        guild_settings_manager.add_message_to_history(message.channel.id, history_entry)

        # Check if AI moderation is enabled for this guild (message.guild is guaranteed non-None here)
        if message.guild and not guild_settings_manager.is_ai_enabled(message.guild.id):
            logger.debug(f"AI moderation disabled for guild {message.guild.name}")
            return

        # Add message to the batching system for AI moderation
        try:
            batch_message = self._create_moderation_message(
                message, 
                actual_content, 
                include_discord_message=True
            )
            await guild_settings_manager.add_message_to_batch(message.channel.id, batch_message)
            logger.debug(f"Added message to batch for channel {message.channel.id}")
        except Exception as e:
            logger.error(f"Error adding message to batch: {e}", exc_info=True)

    @commands.Cog.listener(name='on_message_edit')
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        """
        Handle message edits: refresh rules cache if needed.

        This handler checks if the edited message is in a rules channel
        and triggers a rules cache refresh if necessary.

        Parameters
        ----------
        before:
            The message before editing.
        after:
            The message after editing.
        """
        # Ignore edits from bots or admins
        if discord_utils.is_ignored_author(after.author):
            return

        # If the content didn't change, nothing to do
        if (before.content or "").strip() == (after.content or "").strip():
            return

        # Refresh rules cache if this edit occurred in a rules channel
        if isinstance(after.channel, discord.abc.GuildChannel):
            await rules_manager.refresh_rules_if_channel(after.channel)


def setup(discord_bot_instance):
    """
    Register the MessageListenerCog with the bot.

    Parameters
    ----------
    discord_bot_instance:
        The Discord bot instance to add this cog to.
    """
    # Some unit tests pass a SimpleNamespace instead of a full bot object
    # (no add_cog). Be tolerant in that case and simply return after
    # constructing the cog.
    cog = MessageListenerCog(discord_bot_instance)
    try:
        add_cog = getattr(discord_bot_instance, "add_cog")
    except Exception:
        # No add_cog available (e.g., tests); nothing more to do.
        return

    # If the bot provides add_cog, register the cog normally.
    add_cog(cog)