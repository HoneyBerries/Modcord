"""
Event handlers cog for the Discord Moderation Bot.
"""

import asyncio
import discord
from typing import Union, Optional

from discord.ext import commands

from modcord.ai.ai_model import moderation_processor
import modcord.bot.bot_helper as bot_helper
from modcord.bot.bot_settings import bot_settings
from modcord.bot.bot_helper import rule_channel_pattern
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
		return bot_settings.is_ai_enabled(guild.id)

	async def refresh_rules_cache_if_rules_channel(self, channel: discord.abc.Messageable) -> None:
		"""If the given channel looks like a rules channel, refresh the rules cache.

		This centralizes the rules-channel detection and cache-refresh call so
		it can be reused by multiple event handlers (message create/edit).
		"""
		# Only TextChannel has a guaranteed .name attribute and is a candidate
		if isinstance(channel, discord.TextChannel) and isinstance(channel.name, str) and rule_channel_pattern.search(channel.name):
			try:
				await bot_helper.refresh_rules_cache(self.bot, bot_settings.server_rules_cache)
				logger.info(f"Rules cache refreshed immediately due to activity in rules channel: {channel.name}")
			except Exception as e:
				logger.error(f"Failed to refresh rules cache for channel {channel}: {e}")

	async def _process_message_batch(self, channel_id: int, messages: list[dict]) -> None:
		"""
		Process a batch of messages from a single channel after 15-second collection period.
		
		Args:
			channel_id: The Discord channel ID
			messages: List of message dicts collected over 15 seconds
		"""
		try:
			logger.info(f"Processing batch of {len(messages)} messages for channel {channel_id}")
			
			if not messages:
				logger.debug(f"Empty batch for channel {channel_id}, skipping")
				return
			
			# Get guild info from the first message for server rules
			first_message = messages[0]
			guild_id = first_message.get("guild_id")
			server_rules = bot_settings.get_server_rules(guild_id) if guild_id else ""
			
			# Check if AI moderation is enabled for this guild
			if guild_id and not bot_settings.is_ai_enabled(guild_id):
				logger.debug(f"AI moderation disabled for guild {guild_id}, skipping batch")
				return
			
			# Prepare messages for AI processing (remove Discord-specific data)
			ai_messages = []
			for msg in messages:
				ai_messages.append({
					"user_id": msg["user_id"],
					"username": msg["username"], 
					"content": msg["content"],
					"message_id": msg["message_id"],
					"timestamp": msg["timestamp"],
					"image_summary": msg["image_summary"]
				})
			
			# Process the batch with AI
			actions = await moderation_processor.get_batch_moderation_actions(
				channel_id=channel_id,
				messages=ai_messages,
				server_rules=server_rules
			)
			
			logger.info(f"AI returned {len(actions)} actions for channel {channel_id}")
			
			# Apply each action
			for action_data in actions:
				try:
					await self._apply_batch_action(action_data, messages, channel_id)
				except Exception as e:
					logger.error(f"Error applying action {action_data} in channel {channel_id}: {e}")
					
		except Exception as e:
			logger.error(f"Error processing message batch for channel {channel_id}: {e}")

	async def _apply_batch_action(self, action_data: dict, original_messages: list[dict], channel_id: int) -> None:
		"""
		Apply a single moderation action from a batch response.
		
		Args:
			action_data: Action dict with user_id, action, reason, etc.
			original_messages: Original message batch with Discord message objects
			channel_id: Channel ID for context
		"""
		try:
			user_id_str = action_data.get("user_id", "")
			action_type_str = action_data.get("action", "null")
			reason = action_data.get("reason", "No reason provided.")
			message_ids = action_data.get("message_ids", [])
			
			if action_type_str == "null" or not user_id_str:
				return
				
			# Convert action string to ActionType enum
			try:
				from modcord.util.actions import ActionType
				action_type = ActionType(action_type_str.lower())
			except ValueError:
				logger.warning(f"Unknown action type '{action_type_str}', skipping")
				return
			
			# Find the user's message(s) in the original batch
			target_user_id = int(user_id_str)
			user_messages = [msg for msg in original_messages if msg.get("user_id") == target_user_id]
			
			if not user_messages:
				logger.warning(f"No messages found for user {user_id_str} in batch for channel {channel_id}")
				return
			
			# Use the most recent message for the action (Discord message object)
			target_message_obj = user_messages[-1].get("message_obj")
			if not target_message_obj:
				logger.warning(f"No Discord message object found for user {user_id_str}")
				return
			
			logger.info(f"Applying {action_type_str} action to user {user_id_str} in channel {channel_id}: {reason}")
			
			# Await the batch actions
			await bot_helper.take_batch_action(
				action=action_type, 
				reason=reason, 
				message=target_message_obj, 
				bot_user=self.bot.user,
				message_ids=message_ids,
				timeout_duration=action_data.get("timeout_duration"),
				ban_duration=action_data.get("ban_duration")
			)
			
		except Exception as e:
			logger.error(f"Error applying batch action {action_data}: {e}")

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
		bot_settings.set_batch_processing_callback(self._process_message_batch)
		
		logger.info("-" * 60)

	async def refresh_rules_cache_task(self):
		"""
		Background task to refresh server rules cache.
		"""
		try:
			await bot_helper.refresh_rules_cache(self.bot, bot_settings.server_rules_cache)
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
		message_data = {
			"role": "user", # for the AI model, not Discord's things
			"user_id": message.author.id,
			"content": actual_content            
		}

		bot_settings.add_message_to_history(message.channel.id, message_data)

		# Respect per-guild AI moderation toggle
		if not self._is_ai_moderation_enabled(message.guild):
			if message.guild:
				logger.debug(f"AI moderation disabled for guild {message.guild.name}; skipping AI filtration.")
			return

		# Add message to the batching system instead of immediate processing
		try:
			batch_message_data = {
				"user_id": message.author.id,
				"username": str(message.author),
				"content": actual_content,
				"message_id": str(message.id),
				"timestamp": message.created_at.replace(tzinfo=None).isoformat() + "Z",
				"image_summary": None,  # TODO: Add image summary support in future
				"guild_id": message.guild.id if message.guild else None,  # Store guild for rules lookup
				"message_obj": message  # Store Discord message object for action application
			}
			
			await bot_settings.add_message_to_batch(message.channel.id, batch_message_data)
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