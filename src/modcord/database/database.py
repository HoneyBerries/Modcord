"""
Database initialization and connection management for SQLite.

This module provides async database operations using aiosqlite through a
centralized Database class.
"""

import aiosqlite
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from modcord.util.logger import get_logger

logger = get_logger("database")

# Database file path
DB_PATH = Path("./data/app.db").resolve()


class Database:
    """
    Central database management class for all moderation and guild configuration operations.
    
    This class provides:
    - Database initialization and schema management
    - Connection management
    - Moderation action logging
    - User history queries
    """
    
    def __init__(self, db_path: Path = DB_PATH):
        """
        Initialize the Database manager.
        
        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
    
    def get_connection(self) -> aiosqlite.Connection:
        """
        Get an async database connection for use in a context manager.
        
        Returns:
            aiosqlite.Connection: Async database connection object.
        """
        return aiosqlite.connect(self.db_path)
    
    async def initialize_database(self) -> bool:
        """
        Initialize the SQLite database and create all required tables and indexes.
        
        Creates the following tables if they don't exist:
        - guild_settings: Per-guild AI and moderation configuration
        - channel_guidelines: Channel-specific moderation guidelines
        - moderation_actions: Historical log of all moderation actions
        - schema_version: Database schema version tracking
        
        Also creates indexes, triggers, and enables SQLite optimizations:
        - Foreign key enforcement
        - Write-Ahead Logging (WAL) for better concurrency
        - Automatic timestamp updates on record changes
        
        Returns:
            bool: True if initialization succeeded, False if any errors occurred.
        """
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            async with self.get_connection() as db:
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
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        auto_review_enabled INTEGER NOT NULL DEFAULT 1
                    )
                """)
                
                # Attempt to add new columns if they don't exist (for existing DBs)
                try:
                    await db.execute("ALTER TABLE guild_settings ADD COLUMN auto_review_enabled INTEGER NOT NULL DEFAULT 1")
                    logger.info("[DATABASE] Added auto_review_enabled column to guild_settings")
                except Exception as e:
                    logger.debug("[DATABASE] auto_review_enabled column already exists or migration failed: %s", e)
                
                # Create normalized tables for moderator roles and review channels
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS guild_moderator_roles (
                        guild_id INTEGER NOT NULL,
                        role_id INTEGER NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (guild_id, role_id),
                        FOREIGN KEY (guild_id) REFERENCES guild_settings(guild_id) ON DELETE CASCADE
                    )
                """)
                
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS guild_review_channels (
                        guild_id INTEGER NOT NULL,
                        channel_id INTEGER NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (guild_id, channel_id),
                        FOREIGN KEY (guild_id) REFERENCES guild_settings(guild_id) ON DELETE CASCADE
                    )
                """)
                
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_moderator_roles_guild
                    ON guild_moderator_roles(guild_id)
                """)
                
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_review_channels_guild
                    ON guild_review_channels(guild_id)
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
            
            logger.info("[DATABASE] Database initialized at %s", self.db_path)
            return True
        except Exception as e:
            logger.error("[DATABASE] Database initialization failed: %s", e)
            return False
    
    async def log_moderation_action(
        self,
        guild_id: int,
        user_id: str,
        action_type: str,
        reason: str,
        metadata: dict | None = None
    ) -> None:
        """
        Log a moderation action to the database for audit trail and history context.
        
        Creates a permanent record of moderation actions that can be queried later
        for user history and moderation analytics.
        
        Args:
            guild_id (int): ID of the guild where the action was taken.
            user_id (str): Snowflake ID of the user affected by the action.
            action_type (str): Type of action (ban, kick, timeout, warn, delete, etc.).
            reason (str): Human-readable reason for the action.
            metadata (dict | None): Optional dictionary with additional action details:
                - ban_duration: Duration in minutes for bans (-1 for permanent)
                - timeout_duration: Duration in minutes for timeouts
                - message_ids: List of deleted message IDs
        """
        metadata_json = json.dumps(metadata) if metadata else None
        
        async with self.get_connection() as db:
            await db.execute(
                """
                INSERT INTO moderation_actions (guild_id, user_id, action_type, reason, metadata)
                VALUES (?, ?, ?, ?, ?)
                """,
                (guild_id, user_id, action_type, reason, metadata_json)
            )
            await db.commit()
        
        logger.debug("[DATABASE] Logged moderation action: %s on user %s in guild %s", action_type, user_id, guild_id)
    
    async def get_past_actions(
        self,
        guild_id: int,
        user_id: str,
        lookback_minutes: int
    ) -> list[dict]:
        """
        Query past moderation actions for a user within a specified time window.
        
        Retrieves the moderation history for a user to provide context to the AI
        model when making moderation decisions. More recent actions may influence
        the severity of automated responses.
        
        Args:
            guild_id (int): ID of the guild to query actions from.
            user_id (str): Snowflake ID of the user to query history for.
            lookback_minutes (int): How many minutes back to query (e.g., 7 days = 10080 minutes).
        
        Returns:
            list[dict]: List of action dictionaries sorted by timestamp (newest first),
                each containing:
                - action_type (str): Type of moderation action
                - reason (str): Reason given for the action
                - timestamp (str): ISO 8601 timestamp of when the action occurred
                - metadata (dict): Additional action-specific data (durations, message IDs, etc.)
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)
        
        async with self.get_connection() as db:
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


# Global database instance
_db_instance = Database()

def get_db() -> Database:
    return _db_instance