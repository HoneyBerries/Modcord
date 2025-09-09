"""
Shared configuration and state management for the Discord Moderation Bot.

Adds persistence of per-guild settings (AI enablement and rules cache)
to a JSON file at data/guild_settings.json.
"""

import collections
from typing import Dict, DefaultDict
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
            lambda: collections.deque(maxlen=50)
        )

        # Per-guild AI moderation toggle (default: enabled)
        self.ai_moderation_enabled: Dict[int, bool] = {}

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
                with self._settings_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        data.setdefault("guilds", {})
                        return data
        except Exception as e:
            logger.error(f"Failed to read settings from {self._settings_path}: {e}")
        return {"guilds": {}}

    def _write_settings(self, data: dict) -> None:
        """Write guild settings JSON to disk directly (no temp file, for Windows compatibility)."""
        try:
            self._ensure_data_dir()
            with self._settings_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to write settings to {self._settings_path}: {e}")

    def _load_from_disk(self) -> None:
        """Populate in-memory caches from JSON on disk."""
        data = self._read_settings()
        guilds = data.get("guilds", {})
        loaded_ai = 0
        loaded_rules = 0
        for gid_str, entry in guilds.items():
            try:
                gid = int(gid_str)
            except ValueError:
                continue
            if isinstance(entry, dict):
                if "ai_enabled" in entry:
                    self.ai_moderation_enabled[gid] = bool(entry.get("ai_enabled", True))
                    loaded_ai += 1
                if "rules" in entry:
                    self.server_rules_cache[gid] = entry.get("rules", "") or ""
                    loaded_rules += 1
        if loaded_ai or loaded_rules:
            logger.info(f"Loaded settings from disk: ai={loaded_ai}, rules={loaded_rules}")

    def _persist_guild(self, guild_id: int) -> None:
        """Persist current in-memory settings for a single guild to disk."""
        data = self._read_settings()
        guilds = data.setdefault("guilds", {})
        entry = guilds.setdefault(str(guild_id), {})
        # Update from in-memory state
        entry["ai_enabled"] = self.ai_moderation_enabled.get(guild_id, True)
        entry["rules"] = self.server_rules_cache.get(guild_id, "")
        self._write_settings(data)


# Global bot configuration instance
bot_config = BotConfig()