"""
Database initialization and connection management for SQLite.

This module provides async database operations using aiosqlite through a
centralized Database class. Uses fcntl file locking for safe concurrent access.

The lock is acquired once during initialize() and released during shutdown().
This ensures exclusive database access for the entire program lifetime.
"""

from __future__ import annotations

import atexit
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


class _DatabaseConnectionContext:
    """Async context manager that initializes connection with pragmas."""
    
    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None
    
    async def __aenter__(self) -> aiosqlite.Connection:
        self._conn = await aiosqlite.connect(self._db_path)
        # Enable foreign keys and WAL mode on every new connection
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.execute("PRAGMA journal_mode = WAL")
        return self._conn
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._conn:
            await self._conn.close()


class Database:
    """
    Central database management class for all moderation and guild configuration operations.
    
    This class provides:
    - Database initialization and schema management via initialize()
    - Clean shutdown and lock release via shutdown()
    - Connection management for database operations
    - Moderation action logging
    - User history queries
    
    Lifecycle:
        1. Call initialize() at program startup - acquires lock and creates schema
        2. Use get_connection(), log_moderation_action(), get_past_actions() as needed
        3. Call shutdown() at program end - releases the lock
    """
    
    def __init__(self, db_path: Path = DB_PATH):
        """
        Initialize the Database manager.
        
        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self.lock_file_path = db_path.parent / (db_path.name + ".lock")
        self._lock_file = None
        self._initialized = False
    
    def _acquire_lock(self) -> bool:
        """
        Acquire an exclusive file lock (internal use only).
        
        Returns:
            bool: True if lock was acquired successfully, False otherwise.
        """
        try:
            self.lock_file_path.parent.mkdir(parents=True, exist_ok=True)
            self.lock_file_path.touch(exist_ok=True)
            self._lock_file = open(self.lock_file_path, "w")
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            atexit.register(self.shutdown)
            logger.info("[DATABASE] Acquired exclusive lock for database")
            return True
        except BlockingIOError:
            logger.error("[DATABASE] Failed to acquire lock: another process is using the database")
            if self._lock_file:
                self._lock_file.close()
                self._lock_file = None
            return False
        except Exception as e:
            logger.error("[DATABASE] Failed to acquire lock: %s", e)
            if self._lock_file:
                self._lock_file.close()
                self._lock_file = None
            return False
    
    def _release_lock(self) -> None:
        """Release the exclusive file lock (internal use only)."""
        try:
            if self._lock_file:
                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
                self._lock_file.close()
                self._lock_file = None
                logger.info("[DATABASE] Released exclusive lock for database")
        except Exception as e:
            logger.error("[DATABASE] Failed to release lock: %s", e)
    
    def get_connection(self) -> _DatabaseConnectionContext:
        """
        Get an async database connection for use in a context manager.
        
        The returned connection automatically enables foreign keys and WAL mode.
        
        Returns:
            _DatabaseConnectionContext: Async context manager yielding a connection.
        """
        return _DatabaseConnectionContext(self.db_path)

    async def initialize(self) -> bool:
        """
        Initialize the database: acquire lock and create schema.
        
        This method should be called once at program startup. It:
        1. Acquires an exclusive file lock (held for program lifetime)
        2. Creates the database directory if needed
        3. Creates all required tables, indexes, and triggers
        
        Returns:
            bool: True if initialization succeeded, False otherwise.
        """
        if self._initialized:
            logger.debug("[DATABASE] Already initialized, skipping")
            return True
        
        # Acquire lock for the entire program lifetime
        if not self._acquire_lock():
            logger.error("[DATABASE] Failed to acquire database lock - another instance may be running")
            return False
        
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            async with self.get_connection() as db:
                # Foreign keys and WAL mode are now enabled by get_connection()
                
                # Guild settings table
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
                
                # Migration: add auto_review_enabled if missing
                try:
                    await db.execute("ALTER TABLE guild_settings ADD COLUMN auto_review_enabled INTEGER NOT NULL DEFAULT 1")
                    logger.info("[DATABASE] Added auto_review_enabled column to guild_settings")
                except Exception:
                    pass  # Column already exists
                
                # Moderator roles table
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS guild_moderator_roles (
                        guild_id INTEGER NOT NULL,
                        role_id INTEGER NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (guild_id, role_id),
                        FOREIGN KEY (guild_id) REFERENCES guild_settings(guild_id) ON DELETE CASCADE
                    )
                """)
                
                # Review channels table
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS guild_review_channels (
                        guild_id INTEGER NOT NULL,
                        channel_id INTEGER NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (guild_id, channel_id),
                        FOREIGN KEY (guild_id) REFERENCES guild_settings(guild_id) ON DELETE CASCADE
                    )
                """)
                
                # Channel guidelines table
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
                
                # Moderation actions table (recreate for schema updates)
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
                
                # Schema version table
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS schema_version (
                        version INTEGER PRIMARY KEY,
                        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Indexes
                await db.execute("CREATE INDEX IF NOT EXISTS idx_moderator_roles_guild ON guild_moderator_roles(guild_id)")
                await db.execute("CREATE INDEX IF NOT EXISTS idx_review_channels_guild ON guild_review_channels(guild_id)")
                await db.execute("CREATE INDEX IF NOT EXISTS idx_moderation_actions_lookup ON moderation_actions(guild_id, user_id, timestamp)")
                await db.execute("CREATE INDEX IF NOT EXISTS idx_channel_guidelines_guild ON channel_guidelines(guild_id)")
                
                # Triggers for automatic timestamp updates
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
                
                await db.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (2)")
                await db.commit()
            
            self._initialized = True
            logger.info("[DATABASE] Database initialized at %s", self.db_path)
            return True
            
        except Exception as e:
            logger.error("[DATABASE] Database initialization failed: %s", e)
            self._release_lock()
            return False
    
    def shutdown(self) -> None:
        """
        Shutdown the database: release the exclusive lock.
        
        This method should be called once at program shutdown.
        It releases the file lock so other processes can access the database.
        """
        if not self._initialized:
            return
        
        self._release_lock()
        self._initialized = False
        logger.info("[DATABASE] Database shutdown complete")
    
    async def log_moderation_action(self, action: ActionData) -> None:
        """
        Log a moderation action to the database.
        
        Args:
            action: ActionData object containing all action details
        """
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
        Query past moderation actions for a user within a time window.
        
        Args:
            guild_id: ID of the guild to query actions from
            user_id: Snowflake ID of the user to query history for
            lookback_minutes: How many minutes back to query
        
        Returns:
            List of ActionData objects sorted by timestamp (newest first)
        """
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


# Global Database instance
database = Database()

def get_db() -> Database:
    """
    Get the global Database instance.
    
    Returns:
        Database: The global Database manager instance.
    """
    return database
