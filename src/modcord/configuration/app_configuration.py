"""Centralized configuration management for Modcord.

This module provides a small, thread-safe helper around a YAML
configuration file (default: config/config.yml) so that the application can
read configuration values from a single shared source without re-parsing the
file repeatedly.

Primary exports
- AppConfig: a thread-safe accessor and loader for application config.
- AISettings: a lightweight, dict-backed wrapper exposing common AI tuning
  fields with attribute accessors while remaining mapping-compatible.
- app_config: a module-global AppConfig instance that callers should reuse.

Usage example:
    from modcord.configuration.app_configuration import app_config

    # Read a value with a default
    value = app_config.get('some_key', 'default')

    # Use the typed AI settings wrapper
    ai = app_config.ai_settings
    if ai.enabled:
        model = ai.model_id

The implementation favors safety and predictable fallbacks: if the YAML file
is missing, malformed, or doesn't contain a top-level mapping, the loader
logs an appropriate message and falls back to an empty configuration.
"""
from __future__ import annotations
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Optional, Iterator
from collections.abc import Mapping

import yaml

from modcord.util.logger import get_logger

logger = get_logger("app_configuration")

# Default path to the YAML configuration file (root-level config/config.yml)
CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "app_config.yml"


class AppConfig:
    """Thread-safe configuration accessor with lazy reload support.

    AppConfig reads a YAML configuration file once (on construction or when
    reload() is called) and caches the result. The instance is protected by a
    reentrant lock so callers can safely read values from multiple threads.

    Typical usage:
        app_config = AppConfig()        # or use the shared instance
        value = app_config.get('key')
        prompt = app_config.format_system_prompt(server_rules)

    The object intentionally returns safe defaults when values are missing or
    when the file cannot be parsed, minimizing the need for callers to guard
    against None everywhere.
    """

    def __init__(self, config_path: Optional[Path | str] = None) -> None:
        self.config_path = Path(config_path) if config_path else CONFIG_PATH
        self.lock = RLock()
        self.data: Dict[str, Any] = {}
        self.reload()

    # --------------------------
    # Private helpers
    # --------------------------
    def load_from_disk(self) -> Dict[str, Any]:
        try:
            with self.config_path.open("r", encoding="utf-8") as file_handle:
                loaded_data = yaml.safe_load(file_handle) or {}
        except FileNotFoundError:
            logger.error("Config file %s not found.", self.config_path)
            return {}
        except Exception as exc:  # noqa: BLE001 - log and fall back to empty config
            logger.error("Failed to load config %s: %s", self.config_path, exc, exc_info=True)
            return {}

        if not isinstance(loaded_data, dict):
            logger.warning("Config file %s must contain a mapping at the top level; ignoring.", self.config_path)
            return {}
        return loaded_data

    # --------------------------
    # Public API
    # --------------------------
    def reload(self) -> Dict[str, Any]:
        """Reload configuration from disk and return the loaded mapping.

        This method grabs the internal lock, re-reads the YAML file, and
        replaces the in-memory cache. It returns the raw mapping that was
        loaded (which will be an empty dict on error).
        """
        with self.lock:
            self.data = self.load_from_disk()
            return self.data

    @property
    def data(self) -> Dict[str, Any]:
        """Return the current cached configuration mapping.

        The returned dict is the internal cache (shallow reference). Callers
        should not mutate it; use get(...) or the provided convenience
        properties instead.
        """
        with self.lock:
            return self.data

    def get(self, key: str, default: Any = None) -> Any:
        """Safe lookup for top-level configuration keys.

        Returns the value for `key` if present, otherwise `default`.
        """
        with self.lock:
            return self.data.get(key, default)

    # --------------------------
    # High-level shortcuts
    # --------------------------
    @property
    def server_rules(self) -> str:
        """Return the configured server rules as a string (or empty string).

        The value is coerced to a string so callers can safely embed it into
        prompts without additional checks.
        """
        with self.lock:
            value = self.data.get("server_rules", "")
        return str(value or "")

    @property
    def system_prompt_template(self) -> str:
        """Return the configured system prompt template (or empty string).

        Templates are expected to use Python format placeholders. Use
        format_system_prompt(...) to render with server rules inserted.
        """
        with self.lock:
            value = self.data.get("system_prompt", "")
        return str(value or "")

    @property
    def ai_settings(self) -> "AISettings":
        """Return the AI settings wrapped in an AISettings helper.

        The wrapper provides both attribute-style access for common fields and
        mapping semantics for backward compatibility.
        """
        with self.lock:
            settings = self.data.get("ai_settings", {})
            if not isinstance(settings, dict):
                settings = {}
            # Wrap raw dict in AISettings for typed access while remaining
            # backward-compatible with dict-like .get(...) usage.
            return AISettings(settings)

    def format_system_prompt(self, server_rules: str = "", *, template_override: Optional[str] = None) -> str:
        """Render the system prompt template with the provided server rules.

        If no template is configured and `server_rules` is provided, the
        returned value will be the server rules. If the template's placeholders
        do not match, we fall back to a readable concatenation so callers still
        receive useful text rather than an exception.
        """
        template = template_override if template_override is not None else self.system_prompt_template
        if not template:
            return server_rules if server_rules else ""

        try:
            return template.format(SERVER_RULES=server_rules)
        except Exception:  # noqa: BLE001 - fallback for mismatched placeholders
            if server_rules:
                return f"{template}\n\nServer rules:\n{server_rules}"
            return template


class AISettings(Mapping):
    """Typed wrapper around the raw AI settings dict.

    This small helper preserves mapping compatibility while exposing commonly
    used fields as properties for clearer call-sites. It intentionally keeps
    a `.get(...)` method so existing code that treats ai_settings as a dict
    continues to work.

    Example:
        s = app_config.ai_settings
        if s.enabled:
            model = s.model_id
        # or use mapping access
        value = s.get('some_custom_knob')
    """

    def __init__(self, data: Optional[Dict[str, Any]] = None) -> None:
        self.data: Dict[str, Any] = data or {}

    # Minimal mapping API
    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    # Mapping protocol methods
    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.data)

    def __len__(self) -> int:
        return len(self.data)

    def as_dict(self) -> Dict[str, Any]:
        return self.data

    # Commonly used fields exposed as properties for convenience
    @property
    def enabled(self) -> bool:
        return bool(self.data.get("enabled", False))

    @property
    def allow_gpu(self) -> bool:
        return bool(self.data.get("allow_gpu", False))

    @property
    def vram_percentage(self) -> float:
        return float(self.data.get("vram_percentage", 0.5))

    @property
    def model_id(self) -> Optional[str]:
        val = self.data.get("model_id")
        return str(val) if val else None

    @property
    def knobs(self) -> Dict[str, Any]:
        k = self.data.get("knobs", {})
        return k if isinstance(k, dict) else {}

    # Allow attribute-like fallback access for any key
    def __getattr__(self, item: str) -> Any:  # pragma: no cover - thin shim
        if item in self.__dict__:
            return self.__dict__[item]
        if item in self.data:
            return self.data[item]
        raise AttributeError(item)

    # (Intentionally no format_system_prompt here — AppConfig provides prompt
    # formatting because templates and server_rules are global application
    # data.)


# Shared application-wide configuration instance
app_config = AppConfig()

__all__ = ["AppConfig", "AISettings", "CONFIG_PATH", "app_config"]