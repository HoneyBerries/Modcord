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
CONFIG_PATH = Path("config/app_config.yml").resolve()


class AppConfig:
    """Thread-safe accessor around the YAML-based application configuration.

    The class caches contents of ``config/app_config.yml``, exposes dictionary-like
    access helpers, and resolves AI-specific settings through :class:`AISettings`.
    """

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self.lock = RLock()
        self._data: Dict[str, Any] = {}
        self.reload()

    # --------------------------
    # Private helpers
    # --------------------------
    def load_from_disk(self) -> Dict[str, Any]:
        try:
            with self.config_path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if not isinstance(data, dict):
                logger.warning("Config file %s must contain a mapping at the top level; ignoring.", self.config_path)
                return {}
            return data
        except FileNotFoundError:
            logger.error("Config file %s not found.", self.config_path)
        except Exception as exc:
            logger.error("Failed to load config %s: %s", self.config_path, exc)
        return {}

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
            self._data = self.load_from_disk()
            return self._data

    @property
    def data(self) -> Dict[str, Any]:
        """Return the current cached configuration mapping.

        The returned dict is the internal cache (shallow reference). Callers
        should not mutate it; use get(...) or the provided convenience
        properties instead.
        """
        with self.lock:
            return self._data

    def get(self, key: str, default: Any = None) -> Any:
        """Safe lookup for top-level configuration keys.

        Returns the value for `key` if present, otherwise `default`.
        """
        with self.lock:
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
        with self.lock:
            value = self._data.get("server_rules") or self._data.get("default_server_rules", "")
        return str(value or "")

    @property
    def channel_guidelines(self) -> str:
        """Return the configured default channel guidelines as a string (or empty string).

        The value is coerced to a string so callers can safely embed it into
        prompts without additional checks.
        """
        with self.lock:
            value = self._data.get("channel_guidelines") or self._data.get("default_channel_guidelines", "")
        return str(value or "")

    @property
    def system_prompt_template(self) -> str:
        """Return the configured system prompt template (or empty string).

        Templates are expected to use Python format placeholders. Use
        format_system_prompt(...) to render with server rules inserted.
        """
        with self.lock:
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
        with self.lock:
            settings = self._data.get("ai_settings", {})
            if not isinstance(settings, dict):
                settings = {}
            
            return AISettings(settings)



class AISettings:
    """Helper exposing typed accessors for AI tuning configuration.

    This class intentionally provides a minimal, explicit API (`get`,
    `as_dict`, and convenience properties) and does not implement the full
    mapping protocol. Callers that previously relied on mapping behavior
    should use the explicit helpers.
    """

    def __init__(self, data: Dict[str, Any] | None = None) -> None:
        self.data: Dict[str, Any] = data or {}

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value for `key` or `default` if missing."""
        return self.data.get(key, default)

    def as_dict(self) -> Dict[str, Any]:
        """Return the underlying mapping (shallow copy recommended by callers)."""
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
    def model_id(self) -> str | None:
        val = self.data.get("model_id")
        return str(val) if val else None

    @property
    def sampling_parameters(self) -> Dict[str, Any]:
        k = self.data.get("sampling_parameters", {})
        return k if isinstance(k, dict) else {}

    @property
    def cpu_offload_gb(self) -> int:
        return int(self.data.get("cpu_offload_gb", 0))


# Shared application-wide configuration instance
app_config = AppConfig(CONFIG_PATH)