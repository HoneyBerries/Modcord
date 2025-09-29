"""Event listener Cog for Modcord.

This cog wires Discord events to the moderation helpers in
``modcord.util.moderation_helper``. It intentionally keeps logic small
and delegates heavy lifting to the helper module.
"""

import asyncio
import discord

from discord.ext import commands

from modcord.configuration.guild_settings import guild_settings_manager
from modcord.ai.ai_moderation_processor import model_state
from modcord.util.moderation_models import ModerationMessage
from modcord.util.logger import get_logger

from modcord.util import moderation_helper
from modcord.util import discord_utils

logger = get_logger("events_listener_cog")


class EventsListenerCog(commands.Cog):
	"""
	Cog containing all bot event handlers.
	"""
	
	def __init__(self, discord_bot_instance):
		# Keep both names for compatibility: some code/tests reference `self.bot`,
		# while the constructor parameter name used here is `discord_bot_instance`.
		self.discord_bot_instance = discord_bot_instance
		self.bot = discord_bot_instance
		logger.info("Events listener cog loaded")

		# The helpers live in `modcord.util.moderation_helper` and are called
		# by passing the cog instance explicitly (no binding to `self`).
	

	@commands.Cog.listener(name='on_ready')
	async def on_ready(self):
		"""Handle bot connection: set presence, start background tasks.

		This registers the periodic rules-refresh task and the batch
		processing callback. Lightweight: the actual work is done in the
		moderation helper module.
		"""
		if self.bot.user:
			await self.update_presence_for_model_state()
			logger.info(f"Bot connected as {self.bot.user} (ID: {self.bot.user.id})")
		else:
			logger.warning("Bot partially connected, but user information not yet available.")
		
		# Start the rules cache refresh task (call helper with self)
		logger.info("Starting server rules cache refresh task...")
		asyncio.create_task(moderation_helper.refresh_rules_cache_task(self))
						
		# Set up batch processing callback for channel-based batching
		logger.info("Setting up batch processing callback...")
		# The callback will be called with the batch; forward it to the helper.
		guild_settings_manager.set_batch_processing_callback(
			lambda batch: moderation_helper.process_message_batch(self, batch)
		)
		
		logger.info("-" * 60)

	
	async def update_presence_for_model_state(self) -> None:
		if not self.bot.user:
			return

		if model_state.available:
			status = discord.Status.online
			activity_name = "over your server while you're asleep!"
		else:
			status = discord.Status.idle
			reason = model_state.init_error or "AI offline"
			activity_name = f"AI offline – {reason}"[:128]

		await self.bot.change_presence(
			status=status,
			activity=discord.Activity(
				type=discord.ActivityType.watching,
				name=activity_name,
			)
		)


	@commands.Cog.listener(name='on_message')
	async def on_message(self, message: discord.Message):
		"""Process incoming guild messages and add them to batching.

		This handler performs quick filtering (ignore DMs, bots, admins,
		empty content) then records the message in the per-guild history
		and forwards it to the batching system. Heavy processing occurs
		asynchronously via the moderation helper pipeline.
		"""
		if message.guild is None:
			# Ignore messages that don't come from a server
			return

		# Ignore messages from bots and administrators
		logger.debug(f"Received message from {message.author}: {message.content}")
		if discord_utils.is_ignored_author(self, message.author):
			logger.debug("Ignoring message from non-user.")
			return

		# Skip empty messages or messages with only whitespace
		actual_content = message.clean_content.strip()
		if actual_content == "":
			return

		# Possibly refresh rules cache if this was posted in a rules channel
		await moderation_helper.refresh_rules_cache_if_rules_channel(self, message.channel)

		# Store message in the channel's history for contextual analysis
		timestamp_iso = message.created_at.replace(tzinfo=None).isoformat() + "Z"
		history_entry = ModerationMessage(
			message_id=str(message.id),
			user_id=str(message.author.id),
			username=str(message.author),
			content=actual_content,
			timestamp=timestamp_iso,
			guild_id=message.guild.id if message.guild else None,
			channel_id=message.channel.id if hasattr(message.channel, "id") else None,
		)
		guild_settings_manager.add_message_to_history(message.channel.id, history_entry)

		# Respect per-guild AI moderation toggle
		if not guild_settings_manager.is_ai_enabled(message.guild.id):
			if message.guild:
				logger.debug(f"AI moderation disabled for guild {message.guild.name}; skipping AI filtration.")
			return

		# Add message to the batching system instead of immediate processing
		try:
			batch_message = ModerationMessage(
				message_id=str(message.id),
				user_id=str(message.author.id),
				username=str(message.author),
				content=actual_content,
				timestamp=timestamp_iso,
				guild_id=message.guild.id if message.guild else None,
				channel_id=message.channel.id if hasattr(message.channel, "id") else None,
				image_summary=None,
				discord_message=message,
			)
			await guild_settings_manager.add_message_to_batch(message.channel.id, batch_message)
			logger.debug(f"Added message from {message.author} to batch for channel {message.channel.id}")
		except Exception as e:
			logger.error(f"Error adding message to batch for {message.author}: {e}")


	@commands.Cog.listener(name='on_message_edit')
	async def on_message_edit(self, before: discord.Message, after: discord.Message):
		"""Handle edited messages and refresh rules cache where relevant.

		Only triggers a refresh when the channel matches the rules-channel
		heuristics; otherwise it's a no-op.
		"""
		# Ignore edits where author is a bot or admin
		if discord_utils.is_ignored_author(self, after.author):
			return

		# If the content didn't change, nothing to do
		if (before.content or "").strip() == (after.content or "").strip():
			return

		# Possibly refresh rules cache if this edit occurred in a rules channel
		await moderation_helper.refresh_rules_cache_if_rules_channel(self, after.channel)


	@commands.Cog.listener(name='on_application_command_error')
	async def on_application_command_error(self, application_context: discord.ApplicationContext, discord_error: discord.DiscordException):
		"""Global handler for application command exceptions.

		Logs the exception and sends a short, safe error reply to the
		command invoker. Designed to avoid leaking internal details.
		"""
		# Ignore commands that don't exist
		if isinstance(discord_error, commands.CommandNotFound):
			return

		# Log the error with traceback
		logger.debug(f"[Error] Error in command '{getattr(application_context.command, 'name', '<unknown>')}': {discord_error}", exc_info=True)

		# Respond to the user with a generic error message
		# Use a try-except block in case the interaction has already been responded to
		try:
			await application_context.respond("A :bug: showed up while running this command.", ephemeral=True)
		except discord.InteractionResponded:
			await application_context.followup.send("A :bug: showed up while running this command.", ephemeral=True)


def setup(discord_bot_instance):
    """Setup function for the cog."""
    discord_bot_instance.add_cog(EventsListenerCog(discord_bot_instance))