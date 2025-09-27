"""Utilities for discovering, caching, and refreshing Discord server rules.

The functions here replace the legacy helpers that previously lived in
``modcord.bot.bot_helper``. Importing from this module keeps all rules-related
logic in one place and avoids dragging unrelated moderation helpers into
callers that only need rule management.
"""

from __future__ import annotations

import asyncio
import re
from typing import Iterable, Optional

import discord

from modcord.configuration.guild_settings import GuildSettings, guild_settings
from modcord.util.logger import get_logger

logger = get_logger("rules_manager")


RULE_CHANNEL_PATTERN = re.compile(
	r"(guidelines|regulations|policy|policies|server[-_]?rules|rules)",
	re.IGNORECASE,
)
"""Heuristic regex used to discover channels that likely contain server rules."""


def _resolve_settings(settings: Optional[GuildSettings]) -> GuildSettings:
	"""Return the provided ``GuildSettings`` or fall back to the shared singleton."""

	return settings if settings is not None else guild_settings


async def collect_rules_text(guild: discord.Guild) -> str:
	"""Collect rule text from channels inside ``guild`` that match ``RULE_CHANNEL_PATTERN``.

	The function walks each matching text channel, combines plain-text content
	with embed descriptions and fields, and returns a newline-separated string.
	Any recoverable errors (missing permissions, transient API issues) are
	logged and skipped so that a single problematic channel does not abort the
	entire fetch.
	"""

	messages: list[str] = []

	for channel in getattr(guild, "text_channels", []):
		channel_name = getattr(channel, "name", "") or ""
		if not isinstance(channel_name, str):
			continue

		if not RULE_CHANNEL_PATTERN.search(channel_name):
			continue

		try:
			async for message in channel.history(oldest_first=True):
				content = getattr(message, "content", "")
				if isinstance(content, str) and content.strip():
					messages.append(content.strip())

				embeds: Iterable[discord.Embed] = getattr(message, "embeds", [])
				for embed in embeds:
					description = getattr(embed, "description", None)
					if isinstance(description, str) and description.strip():
						messages.append(description.strip())

					for field in getattr(embed, "fields", []):
						field_name = getattr(field, "name", "")
						field_value = getattr(field, "value", "")
						if isinstance(field_value, str) and field_value.strip():
							prefix = f"{field_name}: " if field_name else ""
							messages.append(f"{prefix}{field_value}".strip())

		except discord.Forbidden:
			logger.warning("No permission to read rules channel %s in %s", channel_name, guild.name)
		except asyncio.CancelledError:  # pragma: no cover - propagation is intentional
			raise
		except Exception as exc:  # pragma: no cover - defensive guard around discord internals
			logger.warning("Error fetching rules from %s in %s: %s", channel_name, guild.name, exc)

	if not messages:
		logger.info("No rule-like content discovered in guild %s", guild.name)
		return ""

	logger.debug(
		"Collected %s rule messages across %s", len(messages), guild.name
	)
	return "\n\n".join(messages)


async def refresh_guild_rules(
	guild: discord.Guild,
	*,
	settings: Optional[GuildSettings] = None,
) -> str:
	"""Fetch and persist the latest rules text for ``guild``.

	Returns the freshly collected rules text. If collection fails, the cached
	value is left untouched (initialised to an empty string if missing) and the
	exception is propagated to the caller for handling.
	"""

	resolved_settings = _resolve_settings(settings)

	try:
		rules_text = await collect_rules_text(guild)
	except Exception:
		if guild.id not in resolved_settings.server_rules_cache:
			resolved_settings.server_rules_cache[guild.id] = ""
		logger.exception("Failed to collect rules for guild %s", guild.name)
		raise

	resolved_settings.set_server_rules(guild.id, rules_text)

	if rules_text:
		logger.debug(
			"Cached %s characters of rules for guild %s", len(rules_text), guild.name
		)
	else:
		logger.info("Rules fetch for guild %s returned no content", guild.name)

	return rules_text


async def refresh_rules_cache(
	bot: discord.Client,
	*, settings: Optional[GuildSettings] = None,
) -> None:
	"""Refresh cached rules for all guilds the bot is currently in."""

	resolved_settings = _resolve_settings(settings)

	logger.debug("Refreshing server rules cache for %s guilds", len(bot.guilds))

	for guild in bot.guilds:
		try:
			await refresh_guild_rules(guild, settings=resolved_settings)
		except asyncio.CancelledError:
			raise
		except Exception as exc:
			logger.warning("Failed to refresh rules for guild %s: %s", guild.name, exc)
			if guild.id not in resolved_settings.server_rules_cache:
				resolved_settings.server_rules_cache[guild.id] = ""

	logger.debug(
		"Rules cache now has entries for %s guilds",
		len(resolved_settings.server_rules_cache),
	)


async def run_periodic_refresh(
	bot: discord.Client,
	*,
	settings: Optional[GuildSettings] = None,
	interval_seconds: float = 300.0,
) -> None:
	"""Continuously refresh the rules cache on a fixed interval.

	Intended to run inside an ``asyncio.create_task`` call. The coroutine loops
	forever until cancelled, logging and continuing on individual guild errors.
	"""

	resolved_settings = _resolve_settings(settings)

	logger.info(
		"Starting periodic rules refresh (interval=%ss) for %s guilds",
		interval_seconds,
		len(bot.guilds),
	)

	try:
		while True:
			try:
				await refresh_rules_cache(bot, settings=resolved_settings)
			except asyncio.CancelledError:
				raise
			except Exception as exc:
				logger.error("Unexpected error during rules refresh: %s", exc)

			await asyncio.sleep(interval_seconds)
	except asyncio.CancelledError:
		logger.info("Periodic rules refresh cancelled")
		raise


