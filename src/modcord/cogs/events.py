"""
Event handlers cog for the Discord Moderation Bot.
"""

import asyncio
import discord
from typing import Union, Optional
from discord.ext import commands
from ..logger import get_logger
from ..actions import ActionType
from .. import bot_helper
from ..bot_helper import rule_channel_pattern
from ..bot_config import bot_config
from .. import ai_model as ai

logger = get_logger("events_cog")


class EventsCog(commands.Cog):
	"""
	Cog containing all bot event handlers.
	"""
	
	def __init__(self, bot):
		self.bot = bot
		logger.info("Events cog loaded")

	def _is_ignored_author(self, author: Union[discord.User, discord.Member]) -> bool:
		"""Return True if the author should be ignored (bot or server admin)."""
		return author.bot or (
			isinstance(author, discord.Member) and author.guild_permissions.administrator
		)

	def _is_ai_moderation_enabled(self, guild: Optional[discord.Guild]) -> bool:
		"""Return True if AI moderation should run for the given guild.

		If guild is None (DM or similar), treat as enabled.
		"""
		if guild is None:
			return True
		return bot_config.is_ai_enabled(guild.id)

	async def _refresh_rules_cache_if_rules_channel(self, channel: discord.abc.Messageable) -> None:
		"""If the given channel looks like a rules channel, refresh the rules cache.

		This centralizes the rules-channel detection and cache-refresh call so
		it can be reused by multiple event handlers (message create/edit).
		"""
		# Only TextChannel has a guaranteed .name attribute and is a candidate
		if isinstance(channel, discord.TextChannel) and isinstance(channel.name, str) and rule_channel_pattern.search(channel.name):
			try:
				await bot_helper.refresh_rules_cache(self.bot, bot_config.server_rules_cache)
				logger.info(f"Rules cache refreshed immediately due to activity in rules channel: {channel.name}")
			except Exception as e:
				logger.error(f"Failed to refresh rules cache for channel {channel}: {e}")

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
			logger.warning("Bot connected, but user information not yet available.")
		
		# Start the rules cache refresh task
		logger.info("Starting server rules cache refresh task...")
		asyncio.create_task(self._refresh_rules_cache_task())
		
		# Start AI batch processing worker
		logger.info("Starting AI batch processing worker...")
		try:
			# ai is already imported at module level
			ai.start_batch_worker()
			logger.info("[AI] Batch processing worker started.")
		except Exception as e:
			logger.error(f"Failed to start AI batch processing worker: {e}")
		logger.info("-" * 60)

	async def _refresh_rules_cache_task(self):
		"""
		Background task to refresh server rules cache.
		"""
		try:
			await bot_helper.refresh_rules_cache(self.bot, bot_config.server_rules_cache)
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
			logger.debug("Ignoring message from bot or administrator.")
			return

		# Skip empty messages or messages with only whitespace
		actual_content = message.content.strip()
		if not actual_content:
			return

		# Possibly refresh rules cache if this was posted in a rules channel
		await self._refresh_rules_cache_if_rules_channel(message.channel)

		# Store message in the channel's history for contextual analysis
		message_data = {
			"role": "user", # for the AI model, not Discord's things
			"user_id": message.author.id,
			"content": actual_content            
		}

		bot_config.add_message_to_history(message.channel.id, message_data)

		# Get server rules
		server_rules = bot_config.get_server_rules(message.guild.id) if message.guild else ""

		# Respect per-guild AI moderation toggle
		if not self._is_ai_moderation_enabled(message.guild):
			if message.guild:
				logger.debug(f"AI moderation disabled for guild {message.guild.name}; skipping AI filtration.")
			return

		# Get a moderation action from the AI model
		try:
			action, reason = await ai.get_appropriate_action(
				current_message=actual_content,
				history=bot_config.get_chat_history(message.channel.id),
				user_id=message.author.id,
				server_rules=server_rules
			)

			if action != ActionType.NULL:
				await bot_helper.take_action(action, reason, message, self.bot.user)
				
		except Exception as e:
			logger.error(f"Error in AI moderation for message from {message.author}: {e}")

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
		await self._refresh_rules_cache_if_rules_channel(after.channel)

	@commands.Cog.listener(name='on_application_command_error')
	async def on_application_command_error(self, ctx: discord.ApplicationContext, error: discord.DiscordException):
		"""
		Global error handler for all application commands.
		Logs the error and sends a generic error message to the user.
		"""
		# Ignore commands that don't exist
		if isinstance(error, commands.CommandNotFound):
			return

		# Log the error with traceback
		logger.debug(f"[Error] Error in command '{getattr(ctx.command, 'name', '<unknown>')}': {error}", exc_info=True)

		# Respond to the user with a generic error message
		# Use a try-except block in case the interaction has already been responded to
		try:
			await ctx.respond("A :bug: showed up while running this command.", ephemeral=True)
		except discord.InteractionResponded:
			await ctx.followup.send("A :bug: showed up while running this command.", ephemeral=True)