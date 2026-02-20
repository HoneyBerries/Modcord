from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

from modcord.configuration.ai_settings import AISettings
from modcord.util.logger import get_logger

logger = get_logger("app_configuration")


CONFIG_PATH = Path("./config/app_config.yml").resolve()

INFINITY = float("inf")


class AppConfig:
    """File-lock based accessor around the YAML-based application configuration.

    The class caches contents of ``./config/app_config.yml``, exposes dictionary-like
    access helpers, and resolves AI-specific settings through :class:`AISettings`.
    Uses fcntl file locks for safe concurrent access across processes.
    """

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self._data: Dict[str, Any] = {}
        self.reload()

    # --------------------------
    # Private helpers
    # --------------------------
    def load_from_disk(self) -> Dict[str, Any]:
        try:
            with self.config_path.open("r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        
        except FileNotFoundError:
            logger.error("[APP CONFIGURATION] Config file %s not found.", self.config_path)
        except Exception as exc:
            logger.error("[APP CONFIGURATION] Failed to load config %s: %s", self.config_path, exc)
        return {}

    # --------------------------
    # Public API
    # --------------------------
    def reload(self) -> Dict[str, Any]:
        """Reload configuration from disk and return the loaded mapping.

        Re-reads the YAML file and replaces the in-memory cache.
        The load_from_disk method uses fcntl locking for safe file access.
        Returns the raw mapping that was loaded (which will be an empty dict on error).
        """
        self._data = self.load_from_disk()
        return self._data

    @property
    def data(self) -> Dict[str, Any]:
        """Return the current cached configuration mapping.

        The returned dict is the internal cache (shallow reference). Callers
        should not mutate it; use get(...) or the provided convenience
        properties instead.
        """
        return self._data

    def get(self, key: str, default: Any = None) -> Any:
        """Safe lookup for top-level configuration keys.

        Returns the value for `key` if present, otherwise `default`.
        """
        return self._data.get(key, default)

    # --------------------------
    # High-level shortcuts
    # --------------------------
    @property
    def generic_server_rules(self) -> str:
        """Return the configured server rules as a string (or empty string).

        The value is coerced to a string so callers can safely embed it into
        prompts without additional checks.
        """
        return self._data.get("generic_server_rules")

    @property
    def channel_guidelines(self) -> str:
        """Return the configured default channel guidelines as a string (or empty string).

        The value is coerced to a string so callers can safely embed it into
        prompts without additional checks.
        """
        return self._data.get("default_channel_guidelines", "")


    @property
    def system_prompt_template(self) -> str:
        """Return the configured system prompt template (or empty string).

        Templates are expected to use Python format placeholders. Use
        format_system_prompt(...) to render with server rules inserted.
        """
        # Check ai_settings.system_prompt
        ai_settings = self._data.get("ai_settings")
        return ai_settings.get("system_prompt", "")

    @property
    def ai_settings(self) -> AISettings:
        """Return the AI settings wrapped in an AISettings helper.

        The wrapper provides both attribute-style access for common fields and
        mapping semantics for backward compatibility.
        """
        settings = self._data.get("ai_settings")
        return AISettings(settings)

    @property
    def rules_sync_interval(self) -> float:
        """Return the server rules sync interval in seconds.

        This is the interval at which server rules are synced from Discord.
        Default is never (INFINITY).
        """
        cache_config = self._data.get("cache", {})
        return float(cache_config.get("rules_cache_refresh", INFINITY)) if isinstance(cache_config, dict) else INFINITY

    @property
    def guidelines_sync_interval(self) -> float:
        """Return the channel guidelines sync interval in seconds.

        This is the interval at which channel guidelines are synced from Discord.
        Default is never (INFINITY).
        """
        cache_config = self._data.get("cache", {})
        return float(cache_config.get("channel_guidelines_cache_refresh", INFINITY)) if isinstance(cache_config, dict) else INFINITY


    @property
    def moderation_batch_seconds(self) -> float:
        """Return the moderation batch window in seconds.

        Messages received within this window are grouped for batch moderation.
        Default is 15 seconds.
        """
        moderation_config = self._data.get("moderation", {})
        return float(moderation_config.get("moderation_batch_seconds", INFINITY)) if isinstance(moderation_config, dict) else INFINITY

    @property
    def past_actions_lookback_days(self) -> int:
        """Return the historical context lookback in days.

        Used by AI to determine punishment escalation.
        Default is 7 days.
        """
        moderation_config = self._data.get("moderation", {})
        return int(moderation_config.get("past_actions_lookback_days", 0)) if isinstance(moderation_config, dict) else 0

    @property
    def past_actions_lookback_minutes(self) -> int:
        """Return the historical context lookback converted to minutes."""
        return self.past_actions_lookback_days * 24 * 60

    @property
    def history_context_messages(self) -> int:
        """Return the number of recent messages to fetch for context.

        Provides context for violations. Default is 8 messages.
        """
        moderation_config = self._data.get("moderation", {})
        if isinstance(moderation_config, dict):
            return int(moderation_config.get("history_context_messages", 8))
        return 8


# Shared application-wide configuration instance
app_config = AppConfig(CONFIG_PATH)