"""
Automated rules and guidelines discovery and caching.

This package handles dynamic discovery and refresh of moderation context:

- **rules_cache_manager.py**: Discovers and caches both server-wide rules and
  channel-specific guidelines. Auto-discovers rules channels via name pattern
  matching ("rules", "guidelines", "regulations", etc.), extracts text from
  embeds and messages. Channel guidelines come from channel topics. Provides
  periodic refresh with configurable interval to keep cache in sync with
  Discord channel changes.

Rules and guidelines are injected into the AI model's system prompt to provide
context-aware moderation aligned with each server's policies.
"""