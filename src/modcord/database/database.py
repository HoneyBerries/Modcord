"""
Database initialization and connection management for SQLite.

This module provides async database operations using aiosqlite through a
centralized Database class. Uses fcntl file locking for safe concurrent access.
"""

from __future__ import annotations

import aiosqlite
import fcntl
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import List

from modcord.datatypes.action_datatypes import ActionData, ActionType
from modcord.datatypes.discord_datatypes import UserID, GuildID, MessageID
from modcord.util.logger import get_logger

logger = get_logger("database")

# Database file path
DB_PATH = Path("./data/app.db").resolve()


class Database:
    """
    Central database management class for all moderation and guild configuration operations.
    
    This class provides:
    - Database initialization and schema management
    - Connection management with fcntl file locking for concurrent access safety
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
        # Lock file for fcntl-based locking (separate from the actual DB)
        self.lock_file_path = db_path.parent / (db_path.name + ".lock")
        self._lock_file = None
    
    def _acquire_lock(self) -> None:
        """
        Acquire an exclusive file lock for database access.
        
        Creates or opens a separate lock file and acquires an exclusive lock.
        This ensures that only one process can perform database operations at a time.
        """
        try:
            self.lock_file_path.touch(exist_ok=True)
            self._lock_file = open(self.lock_file_path, "w")
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX)
            logger.debug("[DATABASE] Acquired lock for database operations")
        except Exception as e:
            logger.error("[DATABASE] Failed to acquire lock: %s", e)
            raise
    
    def _release_lock(self) -> None:
        """
        Release the exclusive file lock for database access.
        """
        try:
            if self._lock_file:
                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
                self._lock_file.close()
                self._lock_file = None
                logger.debug("[DATABASE] Released lock for database operations")
        except Exception as e:
            logger.error("[DATABASE] Failed to release lock: %s", e)
    
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
        
        Database access is protected by fcntl file locking.
        
        Returns:
            bool: True if initialization succeeded, False if any errors occurred.
        """
        try:
            self._acquire_lock()
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
                    
                    # Drop old moderation_actions table and create new one with proper columns
                    await db.execute("DROP TABLE IF EXISTS moderation_actions")
                    
                    await db.execute("""
                        CREATE TABLE IF NOT EXISTS moderation_actions (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            guild_id INTEGER NOT NULL,
                            user_id TEXT NOT NULL,
                            action TEXT NOT NULL,
                            reason TEXT NOT NULL,
                            timeout_duration INTEGER NOT NULL DEFAULT 0,
                            ban_duration INTEGER NOT NULL DEFAULT 0,
                            message_ids TEXT NOT NULL DEFAULT '',
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
                        INSERT OR IGNORE INTO schema_version (version) VALUES (2)
                    """)
                    await db.commit()
                
                logger.info("[DATABASE] Database initialized at %s", self.db_path)
                return True
            except Exception as e:
                logger.error("[DATABASE] Database initialization failed: %s", e)
                return False
            finally:
                self._release_lock()
        except Exception as e:
            logger.error("[DATABASE] Failed to acquire database lock: %s", e)
            return False
    
    async def log_moderation_action(self, action: ActionData) -> None:
        """
        Log a moderation action to the database for audit trail and history context.
        
        Creates a permanent record of moderation actions that can be queried later
        for user history and moderation analytics. Database access is protected by fcntl lock.
        
        Args:
            action: ActionData object containing all action details
        """
        self._acquire_lock()
        try:
            # Serialize message IDs as comma-separated string
            message_ids_str = ",".join(str(mid) for mid in action.message_ids) if action.message_ids else ""
            
            async with self.get_connection() as db:
                await db.execute(
                    """
                    INSERT INTO moderation_actions (guild_id, user_id, action, reason, timeout_duration, ban_duration, message_ids)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        action.guild_id.to_int(),
                        str(action.user_id),
                        action.action.value,
                        action.reason,
                        action.timeout_duration,
                        action.ban_duration,
                        message_ids_str
                    )
                )
                await db.commit()
        finally:
            self._release_lock()
        
        logger.debug(
            "[DATABASE] Logged moderation action: %s on user %s in guild %s",
            action.action.value,
            action.user_id,
            action.guild_id
        )
    
    async def get_past_actions(
        self,
        guild_id: GuildID,
        user_id: UserID,
        lookback_minutes: int
    ) -> List[ActionData]:
        """
        Query past moderation actions for a user within a specified time window.
        
        Retrieves the moderation history for a user to provide context to the AI
        model when making moderation decisions. Database access is protected by fcntl lock.
        
        Args:
            guild_id: ID of the guild to query actions from
            user_id: Snowflake ID of the user to query history for
            lookback_minutes: How many minutes back to query
        
        Returns:
            List of ActionData objects sorted by timestamp (newest first)
        """
        self._acquire_lock()
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)
            guild_id_int = guild_id.to_int() if isinstance(guild_id, GuildID) else guild_id
            
            async with self.get_connection() as db:
                cursor = await db.execute(
                    """
                    SELECT guild_id, user_id, action, reason, timeout_duration, ban_duration, message_ids, timestamp
                    FROM moderation_actions
                    WHERE guild_id = ? AND user_id = ? AND timestamp >= ?
                    ORDER BY timestamp DESC
                    """,
                    (guild_id_int, str(user_id), cutoff_time.isoformat())
                )
                rows = await cursor.fetchall()
            
            actions: List[ActionData] = []
            for row in rows:
                db_guild_id, db_user_id, action_str, reason, timeout_dur, ban_dur, message_ids_str, _ = row
                
                # Parse message IDs from comma-separated string
                message_ids: List[MessageID] = []
                if message_ids_str:
                    message_ids = [MessageID(mid) for mid in message_ids_str.split(",") if mid]
                
                actions.append(ActionData(
                    guild_id=GuildID(db_guild_id),
                    user_id=UserID(db_user_id),
                    action=ActionType(action_str),
                    reason=reason,
                    timeout_duration=timeout_dur,
                    ban_duration=ban_dur,
                    message_ids=message_ids
                ))
            
            return actions
        finally:
            self._release_lock()


# Global database instance
_db_instance = Database()

def get_db() -> Database:
    return _db_instance