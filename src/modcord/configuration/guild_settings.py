"""
Bot settings: persistent per-guild flags and runtime batching.

Responsibilities:
- Persist per-guild settings (ai_enabled, rules, and action toggles) to data/guild_settings.json
- Cache server rules and per-channel chat history
- Provide a 15s channel message batching mechanism with an async callback

Schema example:
{
  "guilds": {
    "<guild_id>": { "ai_enabled": <bool>, "rules": "<string>" }
  }
}
"""

import collections
import asyncio
from typing import Dict, DefaultDict, Callable, Awaitable, Optional, List, Sequence, Set
from collections import deque
from pathlib import Path
import json
import os
from dataclasses import dataclass
from modcord.util.logger import get_logger
from modcord.util.moderation_datatypes import ActionType, ModerationBatch, ModerationMessage
from modcord.util.message_cache import message_history_cache
from modcord.configuration.app_configuration import app_config

logger = get_logger("guild_settings_manager")


@dataclass
class GuildSettings:
    """Persistent per-guild configuration along with transient batching state."""

    guild_id: int
    ai_enabled: bool = True
    rules: str = ""
    auto_warn_enabled: bool = True
    auto_delete_enabled: bool = True
    auto_timeout_enabled: bool = True
    auto_kick_enabled: bool = True
    auto_ban_enabled: bool = True

    @classmethod
    def from_dict(cls, guild_id: int, payload: Dict[str, object]) -> "GuildSettings":
        """Create a GuildSettings instance from a dictionary payload."""
        if not isinstance(payload, dict):
            return cls(guild_id=guild_id)
        ai_enabled = bool(payload.get("ai_enabled", True))
        rules_raw = payload.get("rules", "")
        rules = str(rules_raw) if rules_raw is not None else ""
        auto_warn_enabled = bool(payload.get("auto_warn_enabled", True))
        auto_delete_enabled = bool(payload.get("auto_delete_enabled", True))
        auto_timeout_enabled = bool(payload.get("auto_timeout_enabled", True))
        auto_kick_enabled = bool(payload.get("auto_kick_enabled", True))
        auto_ban_enabled = bool(payload.get("auto_ban_enabled", True))
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
        """Return a dictionary representation of guild settings for persistence."""
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
    """
    Manager for persistent per-guild settings and transient state.

    Responsibilities:
    - Persist per-guild settings (ai_enabled, rules, action toggles) to data/guild_settings.json
    - Cache server rules and per-channel chat history
    - Provide a 15s channel message batching mechanism with an async callback
    """

    def __init__(self):
        """Instantiate caches, batching queues, and persistence helpers."""
        # Persistence path (root/data/guild_settings.json)
        self.data_dir = Path("data")
        self.settings_path = self.data_dir / "guild_settings.json"

        # Persisted guild settings registry (guild_id -> GuildSettings)
        self.guilds: Dict[int, GuildSettings] = {}

        # Per-channel chat history for AI context
    # self.chat_history is now obsolete; use message_history_cache instead

        # Channel-based message batching system (15-second intervals)
        self.channel_message_batches: DefaultDict[int, List[ModerationMessage]] = collections.defaultdict(list)
        self.channel_batch_timers: Dict[int, asyncio.Task] = {}  # channel_id -> timer task
        self.batch_processing_callback: Optional[Callable[[ModerationBatch], Awaitable[None]]] = None

        # Persistence helpers
        self._persist_lock = asyncio.Lock()
        self._active_persists: Set[asyncio.Task] = set()

        # Load persisted settings (if present)
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
                str(guild_id): settings.to_dict()
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
        """
        Cache and persist rules for the given guild.

        Persistence is scheduled in a non-blocking manner.
        """
        if rules is None:
            rules = ""

        settings = self.ensure_guild(guild_id)
        settings.rules = rules
        logger.debug(f"Updated rules cache for guild {guild_id} (len={len(rules)})")

        self._trigger_persist()

    def add_message_to_history(self, channel_id: int, message: ModerationMessage) -> None:
        """Add a message to the dynamic message cache for Discord API fallback."""
        message_history_cache.add_message(channel_id, message)


    # get_chat_history is now obsolete; use message_history_cache.get_cached_messages if needed

    # --- Channel-based message batching for 15-second intervals ---
    def set_batch_processing_callback(self, callback: Callable[[ModerationBatch], Awaitable[None]]) -> None:
        """Set the async callback invoked when a channel batch is ready."""
        self.batch_processing_callback = callback
        logger.info("Batch processing callback set")

    async def add_message_to_batch(self, channel_id: int, message: ModerationMessage) -> None:
        """Queue a message for the channel's 15s batch and start the timer if needed."""
        # Add message to current batch
        self.channel_message_batches[channel_id].append(message)
        logger.debug(
            "Added message to batch for channel %s, message group size: %d",
            channel_id,
            len(self.channel_message_batches[channel_id]),
        )

        # If this is the first message in the batch, start the timer
        if channel_id not in self.channel_batch_timers:
            self.channel_batch_timers[channel_id] = asyncio.create_task(self.batch_timer(channel_id))
            logger.debug("Started 15-second batch timer for channel %s", channel_id)

    async def batch_timer(self, channel_id: int) -> None:
        """Await the batching window, then invoke the batch callback with messages."""
        try:
            ai_settings = app_config.ai_settings if app_config else {}
            moderation_batch_seconds = float(ai_settings.get("moderation_batch_seconds", 10.0))
            logger.debug("Using moderation_batch_seconds=%s seconds for channel %s", moderation_batch_seconds, channel_id)
            await asyncio.sleep(moderation_batch_seconds)

            # Get the current batch and clear it
            messages = list(self.channel_message_batches[channel_id])
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
                logger.debug("Processing batch for channel %s with %d messages", channel_id, len(messages))
                history_context = await self._resolve_history_context(channel_id, messages)
                if history_context:
                    logger.debug(
                        "Including %d prior messages as context for channel %s",
                        len(history_context),
                        channel_id,
                    )
                batch = ModerationBatch(channel_id=channel_id, messages=messages, history=history_context)
                try:
                    await self.batch_processing_callback(batch)
                except Exception:
                    logger.exception("Exception while processing batch for channel %s", channel_id)
            else:
                logger.debug("No messages or callback for channel %s", channel_id)

        except asyncio.CancelledError:
            logger.debug("Batch timer cancelled for channel %s", channel_id)
            if channel_id in self.channel_batch_timers:
                del self.channel_batch_timers[channel_id]
        except Exception:
            logger.exception("Error in batch timer for channel %s", channel_id)
            if channel_id in self.channel_batch_timers:
                del self.channel_batch_timers[channel_id]

    def cancel_all_batch_timers(self) -> None:
        """
        Cancel and clear all active batch timers (use during shutdown).

        This is synchronous and will request cancellation; call shutdown() to
        await the tasks and ensure cleanup.
        """
        for channel_id, timer_task in list(self.channel_batch_timers.items()):
            timer_task.cancel()
        logger.info("Requested cancellation of all batch timers")

    def _trigger_persist(self) -> None:
        """Schedule a best-effort snapshot of guild settings to disk."""
        payload = self.build_payload()

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            if not self.write_settings(payload):
                logger.error("Failed to persist guild settings synchronously")
            return

        task = loop.create_task(self.write_settings_async(payload))
        self._active_persists.add(task)

        def _cleanup(completed: asyncio.Task) -> None:
            self._active_persists.discard(completed)
            try:
                if not completed.result():
                    logger.error("Failed to persist guild settings snapshot")
            except Exception:
                logger.exception("Error while writing guild settings snapshot")

        task.add_done_callback(_cleanup)

    def schedule_persist(self, guild_id: int) -> bool:  # pragma: no cover - maintained for compatibility
        """Backward-compatible wrapper that triggers a settings persist."""
        self._trigger_persist()
        return True

    async def _resolve_history_context(
        self,
        channel_id: int,
        current_batch: Sequence[ModerationMessage],
    ) -> List[ModerationMessage]:
        """Select prior channel messages to provide as model context.
        
        Uses the message cache and Discord API fallback to fetch historical
        context, ensuring availability even if the bot was offline when
        messages were posted.
        """
        # Build set of message IDs to exclude (current batch)
        current_ids = {str(msg.message_id) for msg in current_batch}

        # Use a default or config-driven value for history context length, or make it a parameter if needed
        default_limit = 20  # You can make this configurable elsewhere if desired
        try:
            history_messages = await message_history_cache.fetch_history_for_context(
                channel_id,
                limit=default_limit,
                exclude_message_ids=current_ids,
            )
            if history_messages:
                logger.debug(
                    "Resolved %d history messages for channel %s from cache/API",
                    len(history_messages),
                    channel_id,
                )
            return history_messages
        except Exception as exc:
            logger.warning(
                "Error fetching history context for channel %s: %s",
                channel_id,
                exc,
            )
            return []

    async def shutdown(self) -> None:
        """Gracefully cancel and await all outstanding batch timers (await on shutdown)."""
        timers = list(self.channel_batch_timers.values())
        self.channel_batch_timers.clear()
        for task in timers:
            task.cancel()
        if timers:
            await asyncio.gather(*timers, return_exceptions=True)

        self.channel_message_batches.clear()

        pending = list(self._active_persists)
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self._active_persists.clear()

        logger.info("Shutdown complete: batch timers cleared")
        logger.info("--------------------------------------------------------------------------------")

    # --- AI moderation enable/disable ---
    def is_ai_enabled(self, guild_id: int) -> bool:
        """Return True if AI moderation is enabled for the guild (default True)."""
        settings = self.guilds.get(guild_id)
        return settings.ai_enabled if settings else True

    def set_ai_enabled(self, guild_id: int, enabled: bool) -> bool:
        """
        Set and persist the AI moderation enabled state for a guild.
        Return whether scheduling the persist was successful or not.
        """
        settings = self.ensure_guild(guild_id)
        settings.ai_enabled = bool(enabled)
        state = "enabled" if enabled else "disabled"
        logger.info("AI moderation %s for guild %s", state, guild_id)
        self._trigger_persist()
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
        logger.debug(
            "Set %s to %s for guild %s",
            field_name,
            enabled,
            guild_id,
        )
        self._trigger_persist()
        return True

    # --- Persistence helpers ---
    def ensure_data_dir(self) -> bool:
        """
        Ensure the data directory exists.

        Return True if the directory exists or was created successfully and
        log errors on failure.
        """
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            return True
        except Exception:
            logger.exception("Failed to ensure data directory at %s", self.data_dir)
            return False

    def read_settings(self) -> dict:
        """
        Load settings JSON from disk.

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
        """Synchronously persist guild settings to disk using an atomic replace."""
        self.ensure_data_dir()
        temp_path = self.settings_path.with_suffix(".tmp")
        try:
            with temp_path.open("w", encoding="utf-8") as fh:
                json.dump(settings_data, fh, ensure_ascii=False, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(temp_path, self.settings_path)
            logger.debug("Persisted guild settings to %s", self.settings_path)
            return True
        except Exception:
            logger.exception("Failed to write settings to %s", self.settings_path)
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass
            return False

    async def write_settings_async(self, settings_data: dict) -> bool:
        """Async helper that offloads :meth:`write_settings` to a worker thread."""
        async with self._persist_lock:
            return await asyncio.to_thread(self.write_settings, settings_data)

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
        """
        Persist a single guild's settings to disk asynchronously.

        Return whether the write was successful or not.

        This version performs only asynchronous writes. Callers must invoke
        and await this coroutine from an active event loop. No synchronous
        file operations or thread-blocking fallbacks are performed here.
        """
        payload = self.build_payload()

        try:
            return await self.write_settings_async(payload)
        except Exception:
            logger.exception("Failed to persist guild %s asynchronously", guild_id)
            return False


# Global guild settings manager instance
guild_settings_manager = GuildSettingsManager()