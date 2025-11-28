"""
Database layer for Modcord using SQLite with async support.

This package manages persistent data storage through a centralized Database class:

- **database.py**: Async SQLite operations via aiosqlite with a Database class that manages:
  - Schema initialization with guild_settings, channel_guidelines, and moderation_actions tables
  - Connection management via private get_connection() method
  - Moderation action logging via log_moderation_action()
  - User history queries via get_past_actions()
  - Global database instance accessible via get_db()

Key Features:
- Class-based architecture for clean, centralized database management
- WAL (Write-Ahead Logging) for better concurrency
- Foreign key constraints for referential integrity
- Automatic timestamp updates via triggers
- Indexed lookups for fast moderation history retrieval
- Legacy function wrappers for backwards compatibility

Usage:
    from modcord.database.database import get_db
    
    db = get_db()
    await db.initialize_database()
    await db.log_moderation_action(guild_id, user_id, "WARN", reason)
    actions = await db.get_past_actions(guild_id, user_id, 7*24*60)
"""