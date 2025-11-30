"""
Database layer for Modcord using SQLite with async support.

This package manages persistent data storage through a centralized Database class:

- **database.py**: Async SQLite operations via aiosqlite with a Database class that manages:
  - Schema initialization via initialize() and cleanup via shutdown()
  - Exclusive file locking for the program lifetime
  - Connection management via get_connection()
  - Moderation action logging via log_moderation_action()
  - User history queries via get_past_actions()
  - Global database instance accessible via get_db()

Key Features:
- Class-based architecture for clean, centralized database management
- Continuous file locking (acquire on initialize, release on shutdown)
- WAL (Write-Ahead Logging) for better concurrency
- Foreign key constraints for referential integrity
- Automatic timestamp updates via triggers
- Indexed lookups for fast moderation history retrieval

Usage:
    from modcord.database.database import get_db
    
    db = get_db()
    await db.initialize()  # Acquire lock and create schema
    await db.log_moderation_action(action)
    actions = await db.get_past_actions(guild_id, user_id, 7*24*60)
    db.shutdown()  # Release lock
"""