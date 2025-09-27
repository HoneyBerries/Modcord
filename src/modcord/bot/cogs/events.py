"""
Event handlers cog for the Discord Moderation Bot.
"""

import asyncio
import discord
from typing import Union, Optional

from discord.ext import commands

from modcord.ai.ai_model import moderation_processor
import modcord.bot.bot_helper as bot_helper
from modcord.configuration.guild_settings import guild_settings_manager
from modcord.bot import rules_manager
from modcord.util.action import ActionData, ActionType, ModerationBatch, ModerationMessage
from modcord.util.logger import get_logger

logger = get_logger("events_cog")


class EventsCog(commands.Cog):
	"""
	Cog containing all bot event handlers.
	"""
	
	def __init__(self, discord_bot_instance):
		# Keep both names for compatibility: some code/tests reference `self.bot`,
		# while the constructor parameter name used here is `discord_bot_instance`.
		self.discord_bot_instance = discord_bot_instance
		self.bot = discord_bot_instance
		logger.info("Events cog loaded")

	def _is_ignored_author(self, author: Union[discord.User, discord.Member]) -> bool:
		"""Return True if the author should be ignored (not discord member)."""
		return author.bot or not isinstance(author, discord.Member)

	def _is_ai_moderation_enabled(self, guild: Optional[discord.Guild]) -> bool:
		"""Return True if AI moderation should run for the given guild.

		If guild is None (DM or similar), treat as enabled.
		"""
		if guild is None:
			return True
		return guild_settings_manager.is_ai_enabled(guild.id)

	async def refresh_rules_cache_if_rules_channel(self, channel: discord.abc.Messageable) -> None:
		"""If the given channel looks like a rules channel, refresh the rules cache.

		This centralizes the rules-channel detection and cache-refresh call so
		it can be reused by multiple event handlers (message create/edit).
		"""
		if isinstance(channel, discord.TextChannel) and isinstance(channel.name, str) and rules_manager.RULE_CHANNEL_PATTERN.search(channel.name):
			guild = channel.guild
			if guild is None:
				return
			try:
				await rules_manager.refresh_guild_rules(guild, settings=guild_settings_manager)
				logger.info(f"Rules cache refreshed immediately due to activity in rules channel: {channel.name}")
			except Exception as e:
				logger.error(f"Failed to refresh rules cache for channel {channel}: {e}")


	async def _process_message_batch(self, batch: ModerationBatch) -> None:
		"""
		Process a batch of messages from a single channel after 15-second collection period.
		
		Args:
			batch: ModerationBatch containing channel id and normalized messages
		"""
		channel_id = batch.channel_id
		try:
			if batch.is_empty():
				logger.debug(f"Empty batch for channel {batch.channel_id}, skipping")
				return
			logger.info(f"Processing batch of {len(batch.messages)} messages for channel {batch.channel_id}")

			messages = batch.messages
			channel_id = batch.channel_id

			# Get guild info from the first message for server rules
			guild_id = messages[0].guild_id
			server_rules = guild_settings_manager.get_server_rules(guild_id) if guild_id else ""
			
			# Check if AI moderation is enabled for this guild
			if guild_id and not guild_settings_manager.is_ai_enabled(guild_id):
				logger.debug(f"AI moderation disabled for guild {guild_id}, skipping batch")
				return

			# Process the batch with AI
			actions = await moderation_processor.get_batch_moderation_actions(
				batch=batch,
				server_rules=server_rules,
			)
			
			logger.info(f"AI returned {len(actions)} actions for channel {channel_id}")
			
			# Apply each action
			for action_data in actions:
				try:
					await self._apply_batch_action(action_data, batch)
				except Exception as e:
					logger.error(f"Error applying action {action_data} in channel {channel_id}: {e}")
					
		except Exception as e:
			logger.error(f"Error processing message batch for channel {channel_id}: {e}")

	async def _apply_batch_action(self, action: ActionData, batch: ModerationBatch) -> None:
		"""
		Apply a single moderation action from a batch response.
		
		Args:
			action: Normalized action decision from the AI model.
			batch: The originating batch of messages (includes Discord message objects).
		"""
		try:
			if action.action is ActionType.NULL or not action.user_id:
				return

			user_messages = [msg for msg in batch.messages if msg.user_id == action.user_id]
			if not user_messages:
				logger.warning(f"No messages found for user {action.user_id} in batch for channel {batch.channel_id}")
				return

			# Use the most recent message that still has the Discord message object reference
			pivot_entry: ModerationMessage | None = None
			for candidate in reversed(user_messages):
				if candidate.discord_message is not None:
					pivot_entry = candidate
					break
			if not pivot_entry:
				logger.warning(f"No Discord message object found for user {action.user_id}")
				return

			logger.info(
				f"Applying {action.action.value} action to user {action.user_id} in channel {batch.channel_id}: {action.reason}"
			)

			await bot_helper.apply_action_decision(
				action=action,
				pivot=pivot_entry,
				bot_user=self.bot.user,
				bot_client=self.bot,
			)
			
		except Exception as e:
			logger.error(f"Error applying batch action {action.to_wire_dict()}: {e}")

	@commands.Cog.listener(name='on_ready')
	async def on_ready(self):
		"""
		Fired when the bot successfully connects to Discord.
		Sets presence, starts background tasks, and logs connection.
		"""
		if self.bot.user:
			await self.bot.change_presence(
				status=discord.Status.online,
				activity=discord.Activity(
					type=discord.ActivityType.watching,
					name="over your server while you're asleep!"
				)
			)
			logger.info(f"Bot connected as {self.bot.user} (ID: {self.bot.user.id})")
		else:
			logger.warning("Bot partially connected, but user information not yet available.")
		
		# Start the rules cache refresh task
		logger.info("Starting server rules cache refresh task...")
		asyncio.create_task(self.refresh_rules_cache_task())
						
		# Set up batch processing callback for channel-based batching
		logger.info("Setting up batch processing callback...")
		guild_settings_manager.set_batch_processing_callback(self._process_message_batch)
		
		logger.info("-" * 60)

	async def refresh_rules_cache_task(self):
		"""
		Background task to refresh server rules cache.
		"""
		try:
			await rules_manager.run_periodic_refresh(self.bot, settings=guild_settings_manager)
		except asyncio.CancelledError:
			logger.info("Rules cache refresh task cancelled")
			raise
		except Exception as e:
			logger.error(f"Error in rules cache refresh task: {e}")

	@commands.Cog.listener(name='on_message')
	async def on_message(self, message: discord.Message):
		"""
		Processes incoming messages for AI-powered moderation.
		"""
		# Ignore messages from bots and administrators
		logger.debug(f"Received message from {message.author}: {message.content}")
		if self._is_ignored_author(message.author):
			logger.debug("Ignoring message from non-user.")
			return

		# Skip empty messages or messages with only whitespace
		actual_content = message.clean_content.strip()
		if actual_content == "":
			return

		# Possibly refresh rules cache if this was posted in a rules channel
		await self.refresh_rules_cache_if_rules_channel(message.channel)

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
		if not self._is_ai_moderation_enabled(message.guild):
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
		"""
		Handle edited messages.
		If the edited message is in a rules channel, refresh the rules cache immediately.
		"""
		# Ignore edits where author is a bot or admin
		if self._is_ignored_author(after.author):
			return

		# If the content didn't change, nothing to do
		if (before.content or "").strip() == (after.content or "").strip():
			return

		# Possibly refresh rules cache if this edit occurred in a rules channel
		await self.refresh_rules_cache_if_rules_channel(after.channel)

	@commands.Cog.listener(name='on_application_command_error')
	async def on_application_command_error(self, application_context: discord.ApplicationContext, discord_error: discord.DiscordException):
		"""
		Global error handler for all application commands.
		Logs the error and sends a generic error message to the user.
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
    discord_bot_instance.add_cog(EventsCog(discord_bot_instance))