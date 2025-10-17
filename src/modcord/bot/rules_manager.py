"""Utilities for discovering, caching, and refreshing Discord server rules.

The functions here replace the legacy helpers that previously lived in
``modcord.bot.bot_helper``. Importing from this module keeps all rules-related
logic in one place and avoids dragging unrelated moderation helpers into
callers that only need rule management.
"""

from __future__ import annotations

import asyncio
import re

import discord

from modcord.configuration.guild_settings import guild_settings_manager
from modcord.util.logger import get_logger

logger = get_logger("rules_manager")


RULE_CHANNEL_PATTERN = re.compile(
	"(guidelines|regulations|policy|policies|server[-_]?rules|rules)",
	re.IGNORECASE,
)
"""Heuristic regex used to discover channels that likely contain server rules."""


def _extract_embed_text(embed: discord.Embed) -> list[str]:
	"""Extract text from embed description and fields."""
	texts = []
	if embed.description and isinstance(embed.description, str):
		texts.append(embed.description.strip())
	texts.extend(
		f"{field.name}: {field.value}".strip() if field.name else field.value.strip()
		for field in embed.fields
		if isinstance(field.value, str) and field.value.strip()
	)
	return texts


def _is_rules_channel(channel: discord.abc.GuildChannel) -> bool:
	"""Check if channel name matches rules pattern."""
	# Handle duck typing for tests - check if it has the required attributes
	name = getattr(channel, "name", None)
	if name is None or not isinstance(name, str):
		return False
	return RULE_CHANNEL_PATTERN.search(name) is not None


async def _collect_channel_messages(channel: discord.TextChannel) -> list[str]:
	"""Collect message and embed text from a single channel.
	
	Logs and skips errors from individual channels so one issue doesn't
	abort the entire collection.
	"""
	messages = []
	try:
		async for message in channel.history(oldest_first=True):
			if message.content and isinstance(message.content, str) and (text := message.content.strip()):
				messages.append(text)
			for embed in message.embeds:
				messages.extend(_extract_embed_text(embed))
	except discord.Forbidden:
		logger.warning("No permission to read rules channel: %s", channel.name)
	except asyncio.CancelledError:
		raise
	except Exception as exc:
		logger.warning("Error fetching rules from channel %s: %s", channel.name, exc)
	return messages


async def collect_rules_text(guild: discord.Guild) -> str:
	"""Collect rule text from channels in guild matching RULE_CHANNEL_PATTERN.

	Returns concatenated rules text, or empty string if none found.
	Errors in individual channels are logged and skipped.
	"""
	all_messages = []
	for channel in guild.text_channels:
		if _is_rules_channel(channel):
			all_messages.extend(await _collect_channel_messages(channel))
	
	if not all_messages:
		logger.debug("No rule-like content discovered in guild %s", guild.name)
		return ""
	
	logger.debug("Collected %d rule messages in guild %s", len(all_messages), guild.name)
	return "\n\n".join(all_messages)


async def refresh_guild_rules(guild: discord.Guild) -> str:
	"""Fetch and persist latest rules for guild.

	Returns collected rules text. If collection fails, cached value
	is left untouched and exception is propagated.
	"""
	try:
		rules_text = await collect_rules_text(guild)
	except Exception:
		logger.exception("Failed to collect rules for guild %s", guild.name)
		raise

	guild_settings_manager.set_server_rules(guild.id, rules_text)
	logger.debug("Cached %d characters of rules for guild %s", len(rules_text), guild.name)
	return rules_text


async def refresh_rules_cache(bot: discord.Client) -> None:
	"""Refresh cached rules for all guilds the bot is in.

	Parameters
	----------
	bot:
		Discord client whose guilds should have their rules refreshed.
	"""
	logger.debug("Refreshing server rules cache for %d guilds", len(bot.guilds))
	for guild in bot.guilds:
		try:
			await refresh_guild_rules(guild)
		except asyncio.CancelledError:
			raise
		except Exception as exc:
			logger.warning("Failed to refresh rules for guild %s: %s", guild.name, exc)


async def run_periodic_refresh(
	bot: discord.Client,
	*,
	interval_seconds: float = 300.0,
) -> None:
	"""Continuously refresh rules cache on a fixed interval.

	Parameters
	----------
	bot:
		Discord client instance whose guilds require periodic refresh.
	interval_seconds:
		Delay between successive refresh runs, in seconds.

	Raises
	------
	asyncio.CancelledError
		Propagated when the enclosing task is cancelled.
	"""
	logger.info(
		"Starting periodic rules refresh (interval=%.1fs) for %d guilds",
		interval_seconds,
		len(bot.guilds),
	)
	try:
		while True:
			try:
				await refresh_rules_cache(bot)
			except asyncio.CancelledError:
				raise
			except Exception as exc:
				logger.error("Unexpected error during rules refresh: %s", exc)
			await asyncio.sleep(interval_seconds)
	except asyncio.CancelledError:
		logger.info("Periodic rules refresh cancelled")
		raise



async def refresh_rules_if_channel(channel: discord.abc.GuildChannel) -> None:
	"""Refresh guild rules if channel matches the rules channel pattern."""
	if not isinstance(channel, discord.TextChannel) or not _is_rules_channel(channel):
		return

	guild = channel.guild
	if not guild:
		return

	try:
		await refresh_guild_rules(guild)
		logger.debug("Rules refreshed from channel: %s", channel.name)
	except Exception as exc:
		logger.error("Failed to refresh rules from channel %s: %s", channel.name, exc)


async def start_periodic_refresh_task(bot: discord.Client, interval_seconds: float = 300.0) -> None:
	"""Start the periodic rules refresh background task."""
	try:
		await run_periodic_refresh(bot, interval_seconds=interval_seconds)
	except asyncio.CancelledError:
		logger.debug("Rules refresh task cancelled")
		raise
	except Exception as exc:
		logger.error("Error in rules refresh task: %s", exc)
