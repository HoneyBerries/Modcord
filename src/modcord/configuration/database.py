"""
Database initialization and connection management for SQLite.

This module provides async database operations using aiosqlite.
"""

import aiosqlite
from pathlib import Path
from typing import Optional
from modcord.util.logger import get_logger

logger = get_logger("database")

# Database file path
DB_PATH = Path("data/app.db")


async def init_database() -> None:
    """
    Initialize the SQLite database and create tables if they don't exist.
    
    This creates a normalized schema for guild settings with proper indexing.
    """
    # Ensure data directory exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    async with get_connection() as db:
        # Enable foreign keys and WAL mode
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("PRAGMA journal_mode = WAL")
        # Create guild_settings table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                ai_enabled INTEGER NOT NULL DEFAULT 1,
                rules TEXT NOT NULL DEFAULT '',
                auto_warn_enabled INTEGER NOT NULL DEFAULT 1,
                auto_delete_enabled INTEGER NOT NULL DEFAULT 1,
                auto_timeout_enabled INTEGER NOT NULL DEFAULT 1,
                auto_kick_enabled INTEGER NOT NULL DEFAULT 1,
                auto_ban_enabled INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create index on guild_id for faster lookups (already indexed as PRIMARY KEY)
        # Create trigger to update updated_at timestamp
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS update_guild_settings_timestamp
            AFTER UPDATE ON guild_settings
            FOR EACH ROW
            BEGIN
                UPDATE guild_settings SET updated_at = CURRENT_TIMESTAMP
                WHERE guild_id = NEW.guild_id;
            END
        """)
        
        # Create schema_version table for future migrations
        await db.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Insert initial schema version
        await db.execute("""
            INSERT OR IGNORE INTO schema_version (version) VALUES (1)
        """)
        
        await db.commit()
        logger.info("Database initialized at %s", DB_PATH)


def get_connection() -> aiosqlite.Connection:
    """
    Get an async database connection.
    
    This returns a connection object that can be used in an async context manager.
    
    Returns:
        aiosqlite.Connection: Async database connection
    """
    # Return connection object that will be used with async context manager
    return aiosqlite.connect(DB_PATH)


def get_connection_sync() -> aiosqlite.Connection:
    """
    Get a synchronous database connection (for testing or initialization).
    
    Returns:
        sqlite3.Connection: Synchronous database connection
    """
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn
