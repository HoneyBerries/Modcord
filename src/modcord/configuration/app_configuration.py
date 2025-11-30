from __future__ import annotations
from pathlib import Path
import fcntl
from typing import Any, Dict
import yaml

from modcord.configuration.ai_settings import AISettings
from modcord.util.logger import get_logger

logger = get_logger("app_configuration")


CONFIG_PATH = Path("./config/app_config.yml").resolve()


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
                # Acquire a shared lock for reading
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                data = yaml.safe_load(f)

                # Release the lock
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                return data
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
    def server_rules(self) -> str:
        """Return the configured server rules as a string (or empty string).

        The value is coerced to a string so callers can safely embed it into
        prompts without additional checks.
        """
        value = self._data.get("server_rules") or self._data.get("default_server_rules", "")
        return str(value or "")

    @property
    def channel_guidelines(self) -> str:
        """Return the configured default channel guidelines as a string (or empty string).

        The value is coerced to a string so callers can safely embed it into
        prompts without additional checks.
        """
        value = self._data.get("channel_guidelines") or self._data.get("default_channel_guidelines", "")
        return str(value or "")

    @property
    def system_prompt_template(self) -> str:
        """Return the configured system prompt template (or empty string).

        Templates are expected to use Python format placeholders. Use
        format_system_prompt(...) to render with server rules inserted.
        """
        # Check ai_settings.system_prompt
        ai_settings = self._data.get("ai_settings", {})
        value = ""
        if isinstance(ai_settings, dict):
            value = ai_settings.get("system_prompt", "")

        return str(value or "")

    @property
    def ai_settings(self) -> AISettings:
        """Return the AI settings wrapped in an AISettings helper.

        The wrapper provides both attribute-style access for common fields and
        mapping semantics for backward compatibility.
        """
        settings = self._data.get("ai_settings", {})
        if not isinstance(settings, dict):
            settings = {}
        return AISettings(settings)

    @property
    def rules_cache_refresh_interval(self) -> float:
        """Return the rules cache refresh interval in seconds.

        This is the interval at which server rules and channel guidelines
        are refreshed from Discord. Default is 600 seconds (10 minutes).

        .. deprecated::
            Use :attr:`rules_sync_interval` instead.
        """
        return self.rules_sync_interval

    @property
    def rules_sync_interval(self) -> float:
        """Return the server rules sync interval in seconds.

        This is the interval at which server rules are synced from Discord.
        Default is 600 seconds (10 minutes).
        """
        # Check new config key first, fall back to legacy key
        sync_config = self._data.get("rules_sync", {})
        if isinstance(sync_config, dict) and "interval_seconds" in sync_config:
            return float(sync_config.get("interval_seconds", 600.0))

        # Fall back to legacy config key
        refresh_config = self._data.get("rules_cache_refresh", {})
        if isinstance(refresh_config, dict):
            return float(refresh_config.get("interval_seconds", 600.0))
        return 600.0

    @property
    def guidelines_sync_interval(self) -> float:
        """Return the channel guidelines sync interval in seconds.

        This is the interval at which channel guidelines are synced from Discord.
        Default is 600 seconds (10 minutes).
        """
        sync_config = self._data.get("guidelines_sync", {})
        if isinstance(sync_config, dict):
            return float(sync_config.get("interval_seconds", 600.0))
        return 600.0


# Shared application-wide configuration instance
app_config = AppConfig(CONFIG_PATH)