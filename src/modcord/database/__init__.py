"""
Database layer for Modcord using SQLite with async support.

This package manages persistent data storage:

- **database.py**: Async SQLite operations via aiosqlite. Initializes database
  schema with guild_settings, channel_guidelines, and moderation_actions tables.
  Provides connection pooling, automatic schema creation with triggers for
  timestamp management, and helper functions for logging actions and querying
  user moderation history.

Key Features:
- WAL (Write-Ahead Logging) for better concurrency
- Foreign key constraints for referential integrity
- Automatic timestamp updates via triggers
- Indexed lookups for fast moderation history retrieval
"""