"""
Database initialization and connection management for SQLite.

This module provides async database operations using aiosqlite.
"""

import aiosqlite
from pathlib import Path
from modcord.util.logger import get_logger

logger = get_logger("database")

# Database file path
DB_PATH = Path("data/app.db").resolve()


async def init_database() -> bool:
    """
    Initialize the SQLite database and create tables if they don't exist.

    Returns:
        bool: True if initialization succeeded, False otherwise.
    """
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        async with get_connection() as db:
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute("PRAGMA journal_mode = WAL")
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
            await db.execute("""
                CREATE TABLE IF NOT EXISTS channel_guidelines (
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    guidelines TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, channel_id),
                    FOREIGN KEY (guild_id) REFERENCES guild_settings(guild_id) ON DELETE CASCADE
                )
            """)
            # Moderation action log used by discord_utils.apply_action_decision and history context
            await db.execute("""
                CREATE TABLE IF NOT EXISTS moderation_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    metadata TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_moderation_actions_lookup
                ON moderation_actions(guild_id, user_id, timestamp)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_channel_guidelines_guild 
                ON channel_guidelines(guild_id)
            """)
            await db.execute("""
                CREATE TRIGGER IF NOT EXISTS update_guild_settings_timestamp
                AFTER UPDATE ON guild_settings
                FOR EACH ROW
                BEGIN
                    UPDATE guild_settings SET updated_at = CURRENT_TIMESTAMP
                    WHERE guild_id = NEW.guild_id;
                END
            """)
            await db.execute("""
                CREATE TRIGGER IF NOT EXISTS update_channel_guidelines_timestamp
                AFTER UPDATE ON channel_guidelines
                FOR EACH ROW
                BEGIN
                    UPDATE channel_guidelines SET updated_at = CURRENT_TIMESTAMP
                    WHERE guild_id = NEW.guild_id AND channel_id = NEW.channel_id;
                END
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                INSERT OR IGNORE INTO schema_version (version) VALUES (1)
            """)
            await db.commit()
        logger.info("Database initialized at %s", DB_PATH)
        return True
    except Exception as e:
        logger.error("Database initialization failed: %s", e)
        return False


def get_connection() -> aiosqlite.Connection:
    """
    Get an async database connection.
    
    This returns a connection object that can be used in an async context manager.
    
    Returns:
        aiosqlite.Connection: Async database connection
    """
    # Return connection object that will be used with async context manager
    return aiosqlite.connect(DB_PATH)


async def log_moderation_action(
    guild_id: int,
    user_id: str,
    action_type: str,
    reason: str,
    metadata: dict | None = None
) -> None:
    """
    Log a moderation action to the database.
    
    Args:
        guild_id: ID of the guild where the action was taken.
        user_id: Snowflake ID of the user the action was taken on.
        action_type: Type of action (ban, kick, timeout, warn, delete).
        reason: Reason for the action.
        metadata: Optional dictionary containing additional info (e.g., duration, message_ids).
    """
    import json
    
    metadata_json = json.dumps(metadata) if metadata else None
    
    async with get_connection() as db:
        await db.execute(
            """
            INSERT INTO moderation_actions (guild_id, user_id, action_type, reason, metadata)
            VALUES (?, ?, ?, ?, ?)
            """,
            (guild_id, user_id, action_type, reason, metadata_json)
        )
        await db.commit()
    
    logger.debug("Logged moderation action: %s on user %s in guild %s", action_type, user_id, guild_id)


async def get_past_actions(
    guild_id: int,
    user_id: str,
    lookback_minutes: int
) -> list[dict]:
    """
    Query past moderation actions for a user within a time window.
    
    Args:
        guild_id: ID of the guild.
        user_id: Snowflake ID of the user.
        lookback_minutes: How many minutes back to query.
    
    Returns:
        List of action dictionaries with keys: action_type, reason, timestamp, metadata.
    """
    import json
    from datetime import datetime, timedelta, timezone
    
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)
    
    async with get_connection() as db:
        cursor = await db.execute(
            """
            SELECT action_type, reason, timestamp, metadata
            FROM moderation_actions
            WHERE guild_id = ? AND user_id = ? AND timestamp >= ?
            ORDER BY timestamp DESC
            """,
            (guild_id, user_id, cutoff_time.isoformat())
        )
        rows = await cursor.fetchall()
    
    actions = []
    for row in rows:
        action_type, reason, timestamp, metadata_json = row
        metadata = json.loads(metadata_json) if metadata_json else {}
        actions.append({
            "action_type": action_type,
            "reason": reason,
            "timestamp": timestamp,
            "metadata": metadata
        })
    
    return actions
