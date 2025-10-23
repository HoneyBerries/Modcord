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
            with self.config_path.open("r", encoding="utf-8") as file_handle:
                loaded_data = yaml.safe_load(file_handle) or {}
        except FileNotFoundError:
            logger.error("Config file %s not found.", self.config_path)
            return {}
        except Exception as exc:
            logger.error("Failed to load config %s: %s", self.config_path, exc)
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
            self._data = self.load_from_disk()

            # Log a concise summary of important AI settings for observability.
            try:
                ai = self.ai_settings
                sampling_parameters = ai.sampling_parameters if hasattr(ai, "sampling_parameters") else {}
                logger.info(
                    "Loaded config: ai.enabled=%s, ai.model_id=%s, sampling_parameters=%s, moderation_batch_seconds=%s",
                    bool(ai.enabled),
                    ai.model_id or "<none>",
                    {k: sampling_parameters.get(k) for k in ("dtype", "max_new_tokens", "temperature") if k in sampling_parameters},
                    ai.get("moderation_batch_seconds", 10.0),
                )
            except Exception:
                # Non-fatal: don't block reload on logging errors
                logger.debug("Loaded config but failed to summarize ai settings for logging")

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
            if "server_rules" in self._data:
                value = self._data.get("server_rules", "")
            else:
                value = self._data.get("default_server_rules", "")
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


class AISettings(Mapping):
    """Mapping-backed helper exposing typed accessors for AI tuning configuration."""

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
    def sampling_parameters(self) -> Dict[str, Any]:
        k = self.data.get("sampling_parameters", {})
        return k if isinstance(k, dict) else {}


# Shared application-wide configuration instance
app_config = AppConfig(CONFIG_PATH)