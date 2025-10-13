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
import concurrent.futures

from dataclasses import dataclass

from modcord.util.logger import get_logger
from modcord.util.moderation_datatypes import ActionType, ModerationBatch, ModerationMessage
from modcord.configuration.app_configuration import app_config

logger = get_logger("guild_settings_manager")


@dataclass
class GuildSettings:
    """Persistent per-guild configuration along with transient batching state."""

    guild_id: int
    ai_enabled: bool = True
    rules: str = ""
    auto_warn_enabled: bool = False
    auto_delete_enabled: bool = False
    auto_timeout_enabled: bool = False
    auto_kick_enabled: bool = False
    auto_ban_enabled: bool = False

    @classmethod
    def from_dict(cls, guild_id: int, payload: Dict[str, object]) -> "GuildSettings":
        if not isinstance(payload, dict):
            return cls(guild_id=guild_id)
        ai_enabled = bool(payload.get("ai_enabled", True))
        rules_raw = payload.get("rules", "")
        rules = str(rules_raw) if rules_raw is not None else ""
        auto_warn_enabled = bool(payload.get("auto_warn_enabled", False))
        auto_delete_enabled = bool(payload.get("auto_delete_enabled", False))
        auto_timeout_enabled = bool(payload.get("auto_timeout_enabled", False))
        auto_kick_enabled = bool(payload.get("auto_kick_enabled", False))
        auto_ban_enabled = bool(payload.get("auto_ban_enabled", False))
        return cls(
            guild_id=guild_id,
            ai_enabled=ai_enabled,
            rules=rules,
            auto_warn_enabled=auto_warn_enabled,
            auto_delete_enabled=auto_delete_enabled,
            auto_timeout_enabled=auto_timeout_enabled,
            auto_kick_enabled=auto_kick_enabled,
            auto_ban_enabled=auto_ban_enabled,
        )

    def to_dict(self) -> Dict[str, object]:
        return {
            "ai_enabled": self.ai_enabled,
            "rules": self.rules,
            "auto_warn_enabled": self.auto_warn_enabled,
            "auto_delete_enabled": self.auto_delete_enabled,
            "auto_timeout_enabled": self.auto_timeout_enabled,
            "auto_kick_enabled": self.auto_kick_enabled,
            "auto_ban_enabled": self.auto_ban_enabled,
        }


ACTION_FLAG_FIELDS: dict[ActionType, str] = {
    ActionType.WARN: "auto_warn_enabled",
    ActionType.DELETE: "auto_delete_enabled",
    ActionType.TIMEOUT: "auto_timeout_enabled",
    ActionType.KICK: "auto_kick_enabled",
    ActionType.BAN: "auto_ban_enabled",
}


class GuildSettingsManager:
    """Manager for persistent per-guild settings and transient state.

    Responsibilities:
    - Persist per-guild settings (ai_enabled, rules) to data/guild_settings.json
    - Cache server rules and per-channel chat history
    - Provide a 15s channel message batching mechanism with an async callback
    """

    def __init__(self):
        """Instantiate caches, batching queues, and persistence helpers."""
        # Persistence path (root/data/guild_settings.json)
        self.data_dir = Path("data")
        self.settings_path = self.data_dir / "guild_settings.json"

        # Internal synchronization primitives
        self.io_lock = asyncio.Lock()

        # Persisted guild settings registry (guild_id -> GuildSettings)
        self.guilds: Dict[int, GuildSettings] = {}

        # Per-channel chat history for AI context
        self.chat_history: DefaultDict[int, deque] = collections.defaultdict(lambda: collections.deque(maxlen=128))

        # Channel-based message batching system (15-second intervals)
        self.channel_message_batches: DefaultDict[int, List[ModerationMessage]] = collections.defaultdict(list)

        self.channel_batch_timers: Dict[int, asyncio.Task] = {}  # channel_id -> timer task

        self.batch_processing_callback: Optional[Callable[[ModerationBatch], Awaitable[None]]] = None

        # Background writer loop and thread so writes can always be scheduled
        # asynchronously from any thread without falling back to synchronous
        # file operations.
        self.writer_loop: Optional[asyncio.AbstractEventLoop] = None
        self.writer_thread: Optional[threading.Thread] = None
        self.writer_ready = threading.Event()
        self.pending_writes: List[concurrent.futures.Future] = []
        # Start the background writer loop
        self.start_writer_loop()

        # Load persisted settings (if present)
        # This is intentionally synchronous and fast; the persisted file is expected small.
        self.load_from_disk()

        logger.info("Guild settings manager initialized")


    def ensure_guild(self, guild_id: int) -> GuildSettings:
        """Create default settings for a guild if none exist and return the record."""
        settings = self.guilds.get(guild_id)
        if settings is None:
            settings = GuildSettings(guild_id=guild_id)
            self.guilds[guild_id] = settings
        return settings

    def build_payload(self) -> Dict[str, Dict[str, Dict[str, object]]]:
        """Serialize all persisted guild settings into a JSON-ready payload."""
        return {
            "guilds": {
                str(guild_id): {
                    "ai_enabled": settings.ai_enabled,
                    "rules": settings.rules,
                    "auto_warn_enabled": settings.auto_warn_enabled,
                    "auto_delete_enabled": settings.auto_delete_enabled,
                    "auto_timeout_enabled": settings.auto_timeout_enabled,
                    "auto_kick_enabled": settings.auto_kick_enabled,
                    "auto_ban_enabled": settings.auto_ban_enabled,
                }
                for guild_id, settings in self.guilds.items()
            }
        }


    def get_guild_settings(self, guild_id: int) -> GuildSettings:
        """Fetch the cached :class:`GuildSettings` instance for the given guild."""
        return self.ensure_guild(guild_id)


    def list_guild_ids(self) -> List[int]:
        """Return a snapshot list of guild IDs currently cached in memory."""
        return list(self.guilds.keys())


    def get_server_rules(self, guild_id: int) -> str:
        """Return cached rules for a guild or an empty string."""
        settings = self.guilds.get(guild_id)
        return settings.rules if settings else ""


    def set_server_rules(self, guild_id: int, rules: str) -> None:
        """Cache and persist rules for the given guild.

        Persistence is scheduled in a non-
        blocking manner.
        """
        
        if rules is None:
            rules = ""

        settings = self.ensure_guild(guild_id)
        settings.rules = rules
        logger.debug(f"Updated rules cache for guild {guild_id} (len={len(rules)})")

        # Persist change by scheduling on the dedicated writer loop
        self.schedule_persist(guild_id)
        logger.debug("Scheduled async persist for guild %s", guild_id)


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
            # Determine configured per-channel batch window (default 15s)
            try:
                batching_cfg = app_config.ai_settings.batching if app_config else {}
                batch_window = float(batching_cfg.get("batch_window", 15.0))
            except Exception:
                batch_window = 15.0
            logger.debug("Using batch_window=%s seconds for channel %s", batch_window, channel_id)
            await asyncio.sleep(batch_window)

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
        # Wait for any pending writes scheduled on the writer loop
        if self.pending_writes:
            for fut in list(self.pending_writes):
                try:
                    # Wait briefly for each pending write to complete
                    fut.result(timeout=2)
                except Exception:
                    # If a future failed or timed out, log and continue
                    logger.exception("Pending write did not complete during shutdown")
            self.pending_writes.clear()

        # Stop the writer loop and join the thread
        self.stop_writer_loop()
        logger.info("Shutdown complete: batch timers cleared and writer stopped")
        logger.info("--------------------------------------------------------------------------------")

    # --- AI moderation enable/disable ---
    def is_ai_enabled(self, guild_id: int) -> bool:
        """Return True if AI moderation is enabled for the guild (default True)."""
        settings = self.guilds.get(guild_id)
        return settings.ai_enabled if settings else True

    def set_ai_enabled(self, guild_id: int, enabled: bool) -> bool:
        """Set and persist the AI moderation enabled state for a guild.
        Return whether scheduling the persist was successful or not.
        """
        settings = self.ensure_guild(guild_id)
        settings.ai_enabled = bool(enabled)
        state = "enabled" if enabled else "disabled"
        logger.info("AI moderation %s for guild %s", state, guild_id)
        # Persist change by scheduling on the dedicated writer loop
        self.schedule_persist(guild_id)
        logger.debug("Scheduled async persist for guild %s", guild_id)
        return True

    def is_action_allowed(self, guild_id: int, action: ActionType) -> bool:
        """Return whether the specified AI action is allowed for the guild."""

        settings = self.ensure_guild(guild_id)
        field_name = ACTION_FLAG_FIELDS.get(action)
        if field_name is None:
            return True
        return bool(getattr(settings, field_name, True))

    def set_action_allowed(self, guild_id: int, action: ActionType, enabled: bool) -> bool:
        """Enable or disable an AI action for the guild and persist the change."""

        field_name = ACTION_FLAG_FIELDS.get(action)
        if field_name is None:
            logger.warning("Attempted to toggle unsupported action %s for guild %s", action, guild_id)
            return False

        settings = self.ensure_guild(guild_id)
        setattr(settings, field_name, bool(enabled))
        logger.info(
            "Set %s to %s for guild %s",
            field_name,
            enabled,
            guild_id,
        )
        self.schedule_persist(guild_id)
        return True

    # --- Persistence helpers ---
    def ensure_data_dir(self) -> bool:
        """Ensure the data directory exists

        Return True if the directory exists or was created successfully and
        log errors on failure."""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            return True
        except Exception:
            logger.exception("Failed to ensure data directory at %s", self.data_dir)
            return False
        

    def read_settings(self) -> dict:
        """Load settings JSON from disk.

        Always returns a mapping with a top-level 'guilds' key. Any disk I/O
        errors are caught and logged; callers will receive an empty structure
        on failure to ensure callers can continue operating.
        """
        try:
            if self.settings_path.exists():
                with self.settings_path.open("r", encoding="utf-8") as file_handle:
                    settings_data = json.load(file_handle)
                    if isinstance(settings_data, dict):
                        settings_data.setdefault("guilds", {})
                        return settings_data
        except Exception:
            logger.exception("Failed to read settings from %s", self.settings_path)
        return {"guilds": {}}

    def write_settings(self, settings_data: dict) -> bool:
        """Write settings JSON to disk atomically (synchronous helper).

        Return whether the write was successful or not.
        
        This performs a write-to-temp-file followed by an atomic replace of the
        target file and fsync to reduce the chance of corruption. It is a
        synchronous helper intended to be executed in a background thread when
        called from the event loop.
        """
        # Ensure dir exists
        self.ensure_data_dir()
        temp_path = None
        try:
            # Create a temp file in the same directory for atomic replace
            fd, temp_path = tempfile.mkstemp(prefix="guild_settings_", dir=str(self.data_dir), text=True)

            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(settings_data, fh, ensure_ascii=False, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            # Atomic replace
            os.replace(str(temp_path), str(self.settings_path))
            logger.debug("Wrote settings to %s", self.settings_path)
            return True
        
        except Exception:
            logger.exception("Failed to write settings to %s", self.settings_path)
            # Clean up temp file if present
            try:
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass
        finally:
            return False
        

    async def write_settings_async(self, settings_data: dict) -> bool:
        """Async wrapper that runs the synchronous writer in a thread.

        Returns whether the write was successful or not.
        
        Uses an async lock to serialize concurrent writes and offloads the
        blocking file work to a thread via asyncio.to_thread.
        """
        # serialize writes with an async lock
        async with self.io_lock:
            return await asyncio.to_thread(self.write_settings, settings_data)

    # --- Background writer loop helpers (ensure async-only persistence) ---
    def start_writer_loop(self) -> None:
        """Start a background thread running an asyncio event loop for persistence."""
        def run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.writer_loop = loop
            self.writer_ready.set()
            try:
                loop.run_forever()
            finally:
                try:
                    loop.run_until_complete(loop.shutdown_asyncgens())
                except Exception:
                    pass
                loop.close()

        th = threading.Thread(target=run, name="guild-settings-writer", daemon=True)
        th.start()
        self.writer_thread = th
        # Wait for loop readiness
        self.writer_ready.wait()

    def stop_writer_loop(self) -> None:
        """Stop the background writer loop and wait for thread exit."""
        if self.writer_loop:
            try:
                self.writer_loop.call_soon_threadsafe(self.writer_loop.stop)
            except Exception:
                pass
        if self.writer_thread:
            self.writer_thread.join()


    def schedule_persist(self, guild_id: int) -> bool:
        """Schedule a persist for a guild on the writer loop without blocking."""
        if not self.writer_loop:
            logger.error("Writer loop not available; cannot schedule persist for %s", guild_id)
            return False

        payload = self.build_payload()
        try:
            fut = asyncio.run_coroutine_threadsafe(self.write_settings_async(payload), self.writer_loop)
            self.pending_writes.append(fut)
        except Exception:
            logger.exception("Failed to schedule persistent write for guild %s", guild_id)
            return False

        return True

    def load_from_disk(self) -> bool:
        """Load persisted guild settings into memory."""
        data = self.read_settings()
        guild_payload = data.get("guilds", {}) if isinstance(data, dict) else {}
        self.guilds.clear()
        loaded = 0
        for guild_id_str, payload in guild_payload.items():
            try:
                guild_id = int(guild_id_str)
            except (TypeError, ValueError):
                continue
            self.guilds[guild_id] = GuildSettings.from_dict(guild_id, payload)
            loaded += 1
        if loaded:
            logger.info("Loaded %d guild settings from disk", loaded)
            return True
        return False

    async def persist_guild(self, guild_id: int) -> bool:
        """Persist a single guild's settings to disk asynchronously.

        Return whether the write was successful or not.

        This version performs only asynchronous writes. Callers must invoke
        and await this coroutine from an active event loop. No synchronous
        file operations or thread-blocking fallbacks are performed here.
        """
        payload = self.build_payload()

        try:
            # Perform the write asynchronously and return its result.
            await self.write_settings_async(payload)
            return True
        except Exception:
            logger.exception("Failed to persist guild %s asynchronously", guild_id)
            return False


# Global guild settings manager instance
guild_settings_manager = GuildSettingsManager()