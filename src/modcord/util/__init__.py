"""
Utility functions and helpers for Modcord.

This package provides reusable utilities:

- **logger.py**: Centralized logging configuration with colored console output,
  rotating file handlers, and per-session log aggregation. Suppresses noise from
  verbose libraries (vLLM, transformers, Discord internals). Uses prompt_toolkit
  for non-blocking console I/O.

- **discord_utils.py**: Low-level Discord API helpers including permission checks,
  message deletion (by ID or time window), moderation action execution,
  notification embeds, and member management utilities. All functions are
  stateless for easy integration with higher-level bot components.

- **image_utils.py**: Image processing for moderation. Downloads and resizes
  images from URLs, generates stable hash IDs for deduplication, handles
  various image formats via Pillow.
"""