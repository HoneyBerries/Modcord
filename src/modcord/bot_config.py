"""
Shared configuration and state management for the Discord Moderation Bot.

Adds persistence of per-guild settings (AI enablement and rules cache)
to a JSON file at data/guild_settings.json.
"""

import collections
import asyncio
import time
from typing import Dict, DefaultDict, Callable, Awaitable
from collections import deque
from pathlib import Path
import json

from .logger import get_logger

logger = get_logger("bot_config")


class BotConfig:
    """
    Centralized configuration and state management for the bot.
    """
    
    def __init__(self):
        # Persistence path (root/data/guild_settings.json)
        self._data_dir = Path(__file__).resolve().parent.parent.parent / "data"
        self._settings_path = self._data_dir / "guild_settings.json"

        # Server rules cache - populated dynamically from Discord channels
        self.server_rules_cache: Dict[int, str] = {}  # guild_id -> rules_text

        # Per-channel chat history for AI context
        self.chat_history: DefaultDict[int, deque] = collections.defaultdict(
            lambda: collections.deque(maxlen=128)
        ) # Channel ID -> deque of message dicts

        # Per-guild AI moderation toggle (default: enabled)
        self.ai_moderation_enabled: Dict[int, bool] = collections.defaultdict(lambda: True)
        
        # Channel-based message batching system (15-second intervals)
        self.channel_message_batches: DefaultDict[int, list] = collections.defaultdict(list)  # channel_id -> list of messages
        self.channel_batch_timers: Dict[int, asyncio.Task] = {}  # channel_id -> timer task
        self.batch_processing_callback: Callable[[int, list], Awaitable[None]] = None  # Callback for processing batches
        
        # Load persisted settings (if present)
        self._load_from_disk()

        logger.info("Bot configuration initialized")
    

    def get_server_rules(self, guild_id: int) -> str:
        """Get server rules for a guild."""
        return self.server_rules_cache.get(guild_id, "")
    
    def set_server_rules(self, guild_id: int, rules: str) -> None:
        """Set server rules for a guild."""
        self.server_rules_cache[guild_id] = rules
        logger.debug(f"Updated rules cache for guild {guild_id}")
        # Persist change
        self._persist_guild(guild_id)
    
    def add_message_to_history(self, channel_id: int, message_data: dict) -> None:
        """Add a message to the channel's chat history."""
        self.chat_history[channel_id].append(message_data)
    
    def get_chat_history(self, channel_id: int) -> list:
        """Get chat history for a channel."""
        return list(self.chat_history[channel_id])

    # --- Channel-based message batching for 15-second intervals ---
    def set_batch_processing_callback(self, callback: Callable[[int, list], Awaitable[None]]) -> None:
        """Set the callback function for processing message batches."""
        self.batch_processing_callback = callback
        logger.debug("Batch processing callback set")

    async def add_message_to_batch(self, channel_id: int, message_data: dict) -> None:
        """
        Add a message to the channel's current batch.
        If this is the first message in a new batch, start a 15-second timer.
        """
        # Add message to current batch
        self.channel_message_batches[channel_id].append(message_data)
        logger.debug(f"Added message to batch for channel {channel_id}, batch size: {len(self.channel_message_batches[channel_id])}")
        
        # If this is the first message in the batch, start the timer
        if channel_id not in self.channel_batch_timers:
            self.channel_batch_timers[channel_id] = asyncio.create_task(
                self._batch_timer(channel_id)
            )
            logger.debug(f"Started 15-second batch timer for channel {channel_id}")

    async def _batch_timer(self, channel_id: int) -> None:
        """
        Wait 15 seconds, then process the batch for the given channel.
        """
        try:
            await asyncio.sleep(15.0)  # 15-second batching window
            
            # Get the current batch and clear it
            messages = self.channel_message_batches[channel_id].copy()
            self.channel_message_batches[channel_id].clear()
            
            # Remove the timer reference
            if channel_id in self.channel_batch_timers:
                del self.channel_batch_timers[channel_id]
            
            # Process the batch if we have messages and a callback
            if messages and self.batch_processing_callback:
                logger.info(f"Processing batch for channel {channel_id} with {len(messages)} messages")
                await self.batch_processing_callback(channel_id, messages)
            else:
                logger.debug(f"No messages or callback for channel {channel_id}")
                
        except asyncio.CancelledError:
            logger.debug(f"Batch timer cancelled for channel {channel_id}")
            # Clean up if cancelled
            if channel_id in self.channel_batch_timers:
                del self.channel_batch_timers[channel_id]
        except Exception as e:
            logger.error(f"Error in batch timer for channel {channel_id}: {e}")
            # Clean up on error
            if channel_id in self.channel_batch_timers:
                del self.channel_batch_timers[channel_id]

    def cancel_all_batch_timers(self) -> None:
        """Cancel all active batch timers (useful for shutdown)."""
        for channel_id, timer_task in list(self.channel_batch_timers.items()):
            timer_task.cancel()
        self.channel_batch_timers.clear()
        logger.info("Cancelled all batch timers")

    # --- AI moderation enable/disable ---
    def is_ai_enabled(self, guild_id: int) -> bool:
        """Return whether AI moderation is enabled for this guild (default True)."""
        return self.ai_moderation_enabled.get(guild_id, True)

    def set_ai_enabled(self, guild_id: int, enabled: bool) -> None:
        """Enable or disable AI moderation for this guild."""
        self.ai_moderation_enabled[guild_id] = enabled
        state = "enabled" if enabled else "disabled"
        logger.info(f"AI moderation {state} for guild {guild_id}")
        # Persist change
        self._persist_guild(guild_id)

    # --- Persistence helpers ---
    def _ensure_data_dir(self) -> None:
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to ensure data directory at {self._data_dir}: {e}")

    def _read_settings(self) -> dict:
        """Read guild settings JSON from disk, returning an object schema {"guilds": {...}}."""
        try:
            if self._settings_path.exists():
                with self._settings_path.open("r", encoding="utf-8") as file_handle:
                    settings_data = json.load(file_handle)
                    if isinstance(settings_data, dict):
                        settings_data.setdefault("guilds", {})
                        return settings_data
        except Exception as e:
            logger.error(f"Failed to read settings from {self._settings_path}: {e}")
        return {"guilds": {}}

    def _write_settings(self, settings_data: dict) -> None:
        """Write guild settings JSON to disk directly (no temp file, for Windows compatibility)."""
        try:
            self._ensure_data_dir()
            with self._settings_path.open("w", encoding="utf-8") as file_handle:
                json.dump(settings_data, file_handle, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to write settings to {self._settings_path}: {e}")

    def _load_from_disk(self) -> None:
        """Populate in-memory caches from JSON on disk."""
        settings_data = self._read_settings()
        guilds_data = settings_data.get("guilds", {})
        loaded_ai_settings_count = 0
        loaded_rules_cache_count = 0
        for guild_id_string, guild_entry in guilds_data.items():
            try:
                guild_id = int(guild_id_string)
            except ValueError:
                continue
            if isinstance(guild_entry, dict):
                if "ai_enabled" in guild_entry:
                    self.ai_moderation_enabled[guild_id] = bool(guild_entry.get("ai_enabled", True))
                    loaded_ai_settings_count += 1
                if "rules" in guild_entry:
                    self.server_rules_cache[guild_id] = guild_entry.get("rules", "") or ""
                    loaded_rules_cache_count += 1
        if loaded_ai_settings_count or loaded_rules_cache_count:
            logger.info(f"Loaded settings from disk")
            logger.debug(f"ai: {loaded_ai_settings_count}, rules: {loaded_rules_cache_count}")

    def _persist_guild(self, guild_id: int) -> None:
        """Persist current in-memory settings for a single guild to disk."""
        settings_data = self._read_settings()
        guilds_data = settings_data.setdefault("guilds", {})
        guild_entry = guilds_data.setdefault(str(guild_id), {})

        # Update from in-memory state
        guild_entry["ai_enabled"] = self.ai_moderation_enabled.get(guild_id, True)
        guild_entry["rules"] = self.server_rules_cache.get(guild_id, "")
        self._write_settings(settings_data)


# Global bot configuration instance
bot_config = BotConfig()