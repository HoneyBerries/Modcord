"""
Configuration management for Modcord.

This package handles all application and guild-level configuration:

- **app_configuration.py**: Thread-safe YAML configuration loader for global settings.
  Provides access to AI settings (model ID, sampling parameters, GPU usage),
  system prompt templates, server rules, channel guidelines, rules cache refresh
  intervals, and past actions lookback windows. Falls back gracefully on missing
  or malformed config files.

- **guild_settings.py**: Per-guild configuration persistence layer. Manages SQLite
  storage of guild-specific settings (AI enabled, action toggles, rules, channel
  guidelines) with in-memory caching for fast access. Handles async persistence
  with non-blocking writes.
"""