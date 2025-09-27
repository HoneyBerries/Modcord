"""
Bot settings: persistent per-guild flags and runtime batching.

Provides a small, clear summary of responsibilities and the JSON schema
used for per-guild persistence.

Schema example:
{
  "guilds": {
    "<guild_id>": { "ai_enabled": <bool>, "rules": "<string>" }
  }
}
"""

import collections
import asyncio
import threading
from typing import Dict, DefaultDict, Callable, Awaitable, Optional, List
from collections import deque
from pathlib import Path
import json
import os
import tempfile
from datetime import datetime

from modcord.util.logger import get_logger
from modcord.util.action import ModerationBatch, ModerationMessage

logger = get_logger("guild_settings")


class GuildSettings:
    """Container for persistent per-guild settings and transient state.

    Responsibilities:
    - Persist per-guild settings (ai_enabled, rules) to data/guild_settings.json
    - Cache server rules and per-channel chat history
    - Provide a 15s channel message batching mechanism with an async callback
    """

    def __init__(self):
        # Persistence path (root/data/guild_settings.json)
        self._data_dir = Path(__file__).resolve().parent.parent.parent / "data"
        self._settings_path = self._data_dir / "guild_settings.json"

        # Internal synchronization primitives
        self._io_lock = asyncio.Lock()          # async lock used by async persistence
        self._sync_lock = threading.Lock()      # fallback sync lock for sync writes

        # Server rules cache - populated dynamically from Discord channels
        self.server_rules_cache: Dict[int, str] = {}  # guild_id -> rules_text

        # Per-channel chat history for AI context
        self.chat_history: DefaultDict[int, deque] = collections.defaultdict(
            lambda: collections.deque(maxlen=128)
        )  # Channel ID -> deque of ModerationMessage

        # Per-guild AI moderation toggle (default: enabled)
        self.ai_moderation_enabled: DefaultDict[int, bool] = collections.defaultdict(lambda: True)

        # Channel-based message batching system (15-second intervals)
        self.channel_message_batches: DefaultDict[int, List[ModerationMessage]] = collections.defaultdict(list)
        self.channel_batch_timers: Dict[int, asyncio.Task] = {}  # channel_id -> timer task
        self.batch_processing_callback: Optional[Callable[[ModerationBatch], Awaitable[None]]] = None

        # Load persisted settings (if present)
        # This is intentionally synchronous and fast; the persisted file is expected small.
        self.load_from_disk()

        logger.info("Bot configuration initialized")


    def get_server_rules(self, guild_id: int) -> str:
        """Return cached rules for a guild or an empty string."""
        return self.server_rules_cache.get(guild_id, "")


    def set_server_rules(self, guild_id: int, rules: str) -> None:
        """Cache and persist rules for the given guild.

        Truncates overly-large rule text to RULE_TEXT_MAX_LENGTH to avoid
        unbounded memory / disk growth. Persistence is scheduled in a non-
        blocking manner when an event loop is available; on startup (no
        running loop) the write will be performed synchronously.
        """
        
        if rules is None:
            rules = ""

        self.server_rules_cache[guild_id] = rules
        logger.debug(f"Updated rules cache for guild {guild_id} (len={len(rules)})")
        # Persist change (async-friendly scheduling)
        self.persist_guild(guild_id)


    def add_message_to_history(self, channel_id: int, message: ModerationMessage) -> None:
        """Append a message to the channel's history deque."""
        self.chat_history[channel_id].append(message)


    def get_chat_history(self, channel_id: int) -> list:
        """Return a list copy of the channel's chat history."""
        return list(self.chat_history[channel_id])


    # --- Channel-based message batching for 15-second intervals ---
    def set_batch_processing_callback(self, callback: Callable[[ModerationBatch], Awaitable[None]]) -> None:
        """Set the async callback invoked when a channel batch is ready."""
        self.batch_processing_callback = callback
        logger.debug("Batch processing callback set")


    async def add_message_to_batch(self, channel_id: int, message: ModerationMessage) -> None:
        """Queue a message for the channel's 15s batch and start the timer if needed."""
        # Add message to current batch
        self.channel_message_batches[channel_id].append(message)
        logger.debug(
            "Added message to batch for channel %s, batch size: %d",
            channel_id,
            len(self.channel_message_batches[channel_id]),
        )

        # If this is the first message in the batch, start the timer
        if channel_id not in self.channel_batch_timers:
            # create_task is safe as long as an event loop is running
            self.channel_batch_timers[channel_id] = asyncio.create_task(self.batch_timer(channel_id))
            logger.debug("Started 15-second batch timer for channel %s", channel_id)


    async def batch_timer(self, channel_id: int) -> None:
        """Await the batching window, then invoke the batch callback with messages."""
        try:
            await asyncio.sleep(15.0)  # 15-second batching window

            # Get the current batch and clear it
            messages = list(self.channel_message_batches[channel_id])
            # Clear the batch storage and remove key to free memory
            self.channel_message_batches[channel_id].clear()
            try:
                del self.channel_message_batches[channel_id]
            except KeyError:
                pass

            # Remove the timer reference
            if channel_id in self.channel_batch_timers:
                del self.channel_batch_timers[channel_id]

            # Process the batch if we have messages and a callback
            if messages and self.batch_processing_callback:
                logger.info("Processing batch for channel %s with %d messages", channel_id, len(messages))
                batch = ModerationBatch(channel_id=channel_id, messages=messages)
                try:
                    await self.batch_processing_callback(batch)
                except Exception:
                    logger.exception("Exception while processing batch for channel %s", channel_id)
            else:
                logger.debug("No messages or callback for channel %s", channel_id)

        except asyncio.CancelledError:
            logger.debug("Batch timer cancelled for channel %s", channel_id)
            # Clean up if cancelled
            if channel_id in self.channel_batch_timers:
                del self.channel_batch_timers[channel_id]
        except Exception:
            logger.exception("Error in batch timer for channel %s", channel_id)
            if channel_id in self.channel_batch_timers:
                del self.channel_batch_timers[channel_id]

    def cancel_all_batch_timers(self) -> None:
        """Cancel and clear all active batch timers (use during shutdown).

        This is synchronous and will request cancellation; call shutdown() to
        await the tasks and ensure cleanup.
        """
        for channel_id, timer_task in list(self.channel_batch_timers.items()):
            timer_task.cancel()
        logger.info("Requested cancellation of all batch timers")

    async def shutdown(self) -> None:
        """Gracefully cancel and await all outstanding batch timers (await on shutdown)."""
        # Request cancellation
        for task in list(self.channel_batch_timers.values()):
            task.cancel()
        # Await tasks to finish
        awaitables = [t for t in list(self.channel_batch_timers.values())]
        for t in awaitables:
            try:
                await t
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Exception waiting for batch timer during shutdown")
        self.channel_batch_timers.clear()
        self.channel_message_batches.clear()
        logger.info("Shutdown complete: batch timers cleared")

    # --- AI moderation enable/disable ---
    def is_ai_enabled(self, guild_id: int) -> bool:
        """Return True if AI moderation is enabled for the guild (default True)."""
        return self.ai_moderation_enabled.get(guild_id, True)

    def set_ai_enabled(self, guild_id: int, enabled: bool) -> None:
        """Set and persist the AI moderation enabled state for a guild."""
        self.ai_moderation_enabled[guild_id] = bool(enabled)
        state = "enabled" if enabled else "disabled"
        logger.info("AI moderation %s for guild %s", state, guild_id)
        # Persist change (async-friendly scheduling)
        self.persist_guild(guild_id)

    # --- Persistence helpers ---
    def ensure_data_dir(self) -> None:
        """Ensure the data directory exists; log errors on failure."""
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            logger.exception("Failed to ensure data directory at %s", self._data_dir)

    def read_settings(self) -> dict:
        """Load settings JSON from disk.

        Always returns a mapping with a top-level 'guilds' key. Any disk I/O
        errors are caught and logged; callers will receive an empty structure
        on failure to ensure callers can continue operating.
        """
        try:
            if self._settings_path.exists():
                with self._settings_path.open("r", encoding="utf-8") as file_handle:
                    settings_data = json.load(file_handle)
                    if isinstance(settings_data, dict):
                        settings_data.setdefault("guilds", {})
                        return settings_data
        except Exception:
            logger.exception("Failed to read settings from %s", self._settings_path)
        return {"guilds": {}}

    def write_settings(self, settings_data: dict) -> None:
        """Write settings JSON to disk atomically (synchronous helper).

        This performs a write-to-temp-file followed by an atomic replace of the
        target file and fsync to reduce the chance of corruption. It is a
        synchronous helper intended to be executed in a background thread when
        called from the event loop.
        """
        # Ensure dir exists
        self.ensure_data_dir()
        temp_fd = None
        temp_path = None
        try:
            # Create a temp file in the same directory for atomic replace
            fd, temp_path = tempfile.mkstemp(prefix="guild_settings_", dir=str(self._data_dir), text=True)
            temp_fd = fd
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(settings_data, fh, ensure_ascii=False, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            # Atomic replace
            os.replace(str(temp_path), str(self._settings_path))
        except Exception:
            logger.exception("Failed to write settings to %s", self._settings_path)
            # Clean up temp file if present
            try:
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass

    async def write_settings_async(self, settings_data: dict) -> None:
        """Async wrapper that runs the synchronous writer in a thread.

        Uses an async lock to serialize concurrent writes and offloads the
        blocking file work to a thread via asyncio.to_thread.
        """
        # serialize writes with an async lock
        async with self._io_lock:
            await asyncio.to_thread(self.write_settings, settings_data)

    def load_from_disk(self) -> None:
        """Load persisted per-guild settings into in-memory caches.

        Called during initialization. Any malformed entries are skipped and
        warnings are logged. Large rule texts are truncated according to the
        module-level RULE_TEXT_MAX_LENGTH to avoid unbounded memory usage.
        """
        settings_data = self.read_settings()
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
                    rules_text = guild_entry.get("rules", "") or ""

                    self.server_rules_cache[guild_id] = rules_text
                    loaded_rules_cache_count += 1
        if loaded_ai_settings_count or loaded_rules_cache_count:
            logger.info("Loaded settings from disk")
            logger.debug("ai: %d, rules: %d", loaded_ai_settings_count, loaded_rules_cache_count)

    def persist_guild(self, guild_id: int) -> None:
        """Persist a single guild's settings to disk.

        If an asyncio event loop is active the
        write will be scheduled asynchronously to avoid blocking handlers.
        When no loop is running (startup path) a synchronous, thread-safe
        write is performed.
        """
        settings_data = self.read_settings()
        guilds_data = settings_data.setdefault("guilds", {})
        guild_entry = guilds_data.setdefault(str(guild_id), {})

        # Update from in-memory state
        guild_entry["ai_enabled"] = self.ai_moderation_enabled.get(guild_id, True)
        guild_entry["rules"] = self.server_rules_cache.get(guild_id, "")

        # Try scheduling an async write if there's a running loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running event loop: perform synchronous write (startup path)
            with self._sync_lock:
                self.write_settings(settings_data)
            return

        # Schedule async write in background; do not await here.
        # Use create_task via call_soon_threadsafe to be safe when called from non-async contexts.
        def _schedule():
            asyncio.create_task(self.write_settings_async(settings_data))

        try:
            loop.call_soon_threadsafe(_schedule)
        except Exception:
            # Fallback: run in a thread
            logger.exception("Failed to schedule async persist; running sync as fallback")
            with self._sync_lock:
                self.write_settings(settings_data)


# Global guild settings instance
guild_settings = GuildSettings()