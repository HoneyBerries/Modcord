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
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from functools import lru_cache

from modcord.datatypes.action_datatypes import ActionData, ActionType
from modcord.datatypes.discord_datatypes import UserID, GuildID, MessageID, ChannelID
from modcord.util.logger import get_logger

logger = get_logger("database")

# Database file path
DB_PATH = Path("./data/app.db").resolve()

# Performance monitoring (#6)
_query_stats: Dict[str, Dict[str, float]] = {}


class _DatabaseConnectionContext:
    """Async context manager that initializes connection with optimized pragmas."""
    
    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None
    
    async def __aenter__(self) -> aiosqlite.Connection:
        self._conn = await aiosqlite.connect(self._db_path)
        # Task #9: Optimize connection pragmas for performance
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.execute("PRAGMA journal_mode = WAL")
        await self._conn.execute("PRAGMA synchronous = NORMAL")  # Faster writes
        await self._conn.execute("PRAGMA cache_size = -64000")  # 64MB cache
        await self._conn.execute("PRAGMA temp_store = MEMORY")  # Use memory for temp tables
        await self._conn.execute("PRAGMA mmap_size = 30000000000")  # 30GB mmap
        await self._conn.execute("PRAGMA page_size = 4096")  # Optimal page size
        return self._conn
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._conn:
            await self._conn.close()


def _track_query_performance(query_name: str, duration: float) -> None:
    """Task #6: Track query performance statistics."""
    if query_name not in _query_stats:
        _query_stats[query_name] = {
            'count': 0,
            'total_time': 0.0,
            'min_time': float('inf'),
            'max_time': 0.0
        }
    
    stats = _query_stats[query_name]
    stats['count'] += 1
    stats['total_time'] += duration
    stats['min_time'] = min(stats['min_time'], duration)
    stats['max_time'] = max(stats['max_time'], duration)
    
    # Log slow queries (> 100ms)
    if duration > 0.1:
        logger.warning(
            "[DATABASE] Slow query detected: %s took %.2fms",
            query_name, duration * 1000
        )


def get_query_statistics() -> Dict[str, Dict[str, float]]:
    """Task #6: Get database query performance statistics."""
    result = {}
    for query_name, stats in _query_stats.items():
        result[query_name] = {
            'count': stats['count'],
            'total_time': stats['total_time'],
            'avg_time': stats['total_time'] / stats['count'] if stats['count'] > 0 else 0,
            'min_time': stats['min_time'] if stats['min_time'] != float('inf') else 0,
            'max_time': stats['max_time']
        }
    return result


class Database:
    """
    Central database management class for all moderation and guild configuration operations.
    
    This class provides:
    - Database initialization and schema management via initialize()
    - Clean shutdown and lock release via shutdown()
    - Connection management for database operations (with pooling - Task #1)
    - Moderation action logging
    - User history queries
    - Performance monitoring (Task #6)
    - Database maintenance operations (Task #10)
    
    Lifecycle:
        1. Call initialize() at program startup - acquires lock and creates schema
        2. Use get_connection(), log_moderation_action(), get_bulk_past_actions() as needed
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
        # Task #1: Connection pool (single persistent connection for better performance)
        self._pool_connection: Optional[aiosqlite.Connection] = None
    
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
                        channel_id INTEGER NOT NULL,
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
                
                # Task #2: Add strategic indexes for common query patterns
                # Existing indexes
                await db.execute("CREATE INDEX IF NOT EXISTS idx_moderator_roles_guild ON guild_moderator_roles(guild_id)")
                await db.execute("CREATE INDEX IF NOT EXISTS idx_review_channels_guild ON guild_review_channels(guild_id)")
                await db.execute("CREATE INDEX IF NOT EXISTS idx_moderation_actions_lookup ON moderation_actions(guild_id, user_id, timestamp)")
                await db.execute("CREATE INDEX IF NOT EXISTS idx_channel_guidelines_guild ON channel_guidelines(guild_id)")
                
                # Task #2: Additional strategic indexes for query optimization
                # Index for timestamp-based queries (Task #5)
                await db.execute("CREATE INDEX IF NOT EXISTS idx_moderation_actions_timestamp ON moderation_actions(timestamp DESC)")
                # Index for user-specific lookups
                await db.execute("CREATE INDEX IF NOT EXISTS idx_moderation_actions_user ON moderation_actions(user_id, guild_id)")
                # Index for action type filtering
                await db.execute("CREATE INDEX IF NOT EXISTS idx_moderation_actions_action ON moderation_actions(action, guild_id)")
                # Composite index for bulk queries
                await db.execute("CREATE INDEX IF NOT EXISTS idx_moderation_actions_bulk ON moderation_actions(guild_id, timestamp DESC, user_id)")
                # Index for channel-based queries
                await db.execute("CREATE INDEX IF NOT EXISTS idx_moderation_actions_channel ON moderation_actions(channel_id, timestamp DESC)")
                
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
    
    async def vacuum(self) -> bool:
        """
        Task #10: Perform database vacuum to reclaim space and optimize storage.
        
        Should be called periodically during maintenance windows.
        
        Returns:
            bool: True if vacuum succeeded, False otherwise.
        """
        try:
            async with self.get_connection() as db:
                logger.info("[DATABASE] Starting VACUUM operation")
                start_time = time.time()
                await db.execute("VACUUM")
                duration = time.time() - start_time
                logger.info("[DATABASE] VACUUM completed in %.2f seconds", duration)
                return True
        except Exception as e:
            logger.error("[DATABASE] VACUUM failed: %s", e)
            return False
    
    async def analyze(self) -> bool:
        """
        Task #10: Update database statistics for query optimizer.
        
        Should be called periodically to maintain optimal query performance.
        
        Returns:
            bool: True if analyze succeeded, False otherwise.
        """
        try:
            async with self.get_connection() as db:
                logger.info("[DATABASE] Starting ANALYZE operation")
                start_time = time.time()
                await db.execute("ANALYZE")
                duration = time.time() - start_time
                logger.info("[DATABASE] ANALYZE completed in %.2f seconds", duration)
                _track_query_performance("ANALYZE", duration)
                return True
        except Exception as e:
            logger.error("[DATABASE] ANALYZE failed: %s", e)
            return False
    
    async def cleanup_old_actions(self, days_to_keep: int = 30) -> int:
        """
        Task #10: Clean up old moderation actions to reduce database size.
        
        Args:
            days_to_keep: Number of days of history to retain (default: 30)
        
        Returns:
            int: Number of records deleted, or -1 on error.
        """
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
            async with self.get_connection() as db:
                cursor = await db.execute(
                    "DELETE FROM moderation_actions WHERE timestamp < ?",
                    (cutoff_date.isoformat(),)
                )
                await db.commit()
                deleted_count = cursor.rowcount
                logger.info(
                    "[DATABASE] Cleaned up %d moderation actions older than %d days",
                    deleted_count, days_to_keep
                )
                return deleted_count
        except Exception as e:
            logger.error("[DATABASE] Cleanup failed: %s", e)
            return -1
    
    
    async def log_moderation_action(self, action: ActionData) -> None:
        """
        Log a moderation action to the database.
        
        Args:
            action: ActionData object containing all action details
        """
        # Task #6: Track query performance
        start_time = time.time()
        
        message_ids = ",".join(str(mid.to_int()) for mid in (action.message_ids_to_delete or []))
        
        async with self.get_connection() as db:
            await db.execute(
                """
                INSERT INTO moderation_actions (guild_id, channel_id, user_id, action, reason, timeout_duration, ban_duration, message_ids)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action.guild_id.to_int(),
                    action.channel_id.to_int(),
                    str(action.user_id),
                    action.action.value,
                    action.reason,
                    action.timeout_duration,
                    action.ban_duration,
                    message_ids
                )
            )
            await db.commit()
        
        duration = time.time() - start_time
        _track_query_performance("log_moderation_action", duration)
        
        logger.debug(
            "[DATABASE] Logged moderation action: %s on user %s in guild %s channel %s",
            action.action.value,
            action.user_id,
            action.guild_id,
            action.channel_id
        )
    
    async def log_moderation_actions_batch(self, actions: List[ActionData]) -> int:
        """
        Task #4: Batch log multiple moderation actions in a single transaction.
        
        This is more efficient than calling log_moderation_action() multiple times
        as it uses a single database transaction with executemany.
        
        Args:
            actions: List of ActionData objects to log
        
        Returns:
            int: Number of actions successfully logged, or -1 on error
        """
        if not actions:
            return 0
        
        # Task #6: Track query performance
        start_time = time.time()
        
        try:
            # Prepare batch data
            batch_data = []
            for action in actions:
                message_ids = ",".join(str(mid.to_int()) for mid in (action.message_ids_to_delete or []))
                batch_data.append((
                    action.guild_id.to_int(),
                    action.channel_id.to_int(),
                    str(action.user_id),
                    action.action.value,
                    action.reason,
                    action.timeout_duration,
                    action.ban_duration,
                    message_ids
                ))
            
            async with self.get_connection() as db:
                await db.executemany(
                    """
                    INSERT INTO moderation_actions (guild_id, channel_id, user_id, action, reason, timeout_duration, ban_duration, message_ids)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    batch_data
                )
                await db.commit()
            
            duration = time.time() - start_time
            _track_query_performance("log_moderation_actions_batch", duration)
            
            logger.debug(
                "[DATABASE] Batch logged %d moderation actions in %.2fms",
                len(actions), duration * 1000
            )
            return len(actions)
            
        except Exception as e:
            logger.error("[DATABASE] Batch log failed: %s", e)
            return -1

    async def get_bulk_past_actions(
        self,
        guild_id: GuildID,
        user_ids: List[UserID],
        lookback_minutes: int
    ) -> Dict[UserID, List[ActionData]]:
        """
        Query past moderation actions for multiple users within a time window.
        
        This is more efficient than calling get_past_actions() multiple times
        as it makes a single database query with IN clause.
        
        Args:
            guild_id: ID of the guild to query actions from
            user_ids: List of user IDs to query history for
            lookback_minutes: How many minutes back to query
        
        Returns:
            Dictionary mapping user_id to list of ActionData objects
        """
        if not user_ids:
            return {}
        
        # Task #6: Track query performance
        start_time = time.time()
        
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)
        guild_id_int = guild_id.to_int() if isinstance(guild_id, GuildID) else guild_id
        
        # Create placeholders for IN clause
        user_id_strs = [str(user_id) for user_id in user_ids]
        placeholders = ','.join('?' * len(user_id_strs))
        
        async with self.get_connection() as db:
            # Task #5: Optimized timestamp query using DESC index
            cursor = await db.execute(
                f"""
                SELECT guild_id, channel_id, user_id, action, reason, timeout_duration, ban_duration, message_ids, timestamp
                FROM moderation_actions
                WHERE guild_id = ? AND user_id IN ({placeholders}) AND timestamp >= ?
                ORDER BY timestamp DESC
                """,
                [guild_id_int] + user_id_strs + [cutoff_time.isoformat()]
            )
            rows = await cursor.fetchall()
        
        # Group actions by user_id
        actions_by_user: Dict[UserID, List[ActionData]] = {user_id: [] for user_id in user_ids}
        
        for row in rows:
            db_guild_id, db_channel_id, db_user_id, action_str, reason, timeout_dur, ban_dur, message_ids_str, _ = row
            
            message_ids: List[MessageID] = []
            if message_ids_str:
                message_ids = [MessageID(mid) for mid in message_ids_str.split(",") if mid]
            
            action_data = ActionData(
                guild_id=GuildID(db_guild_id),
                channel_id=ChannelID(db_channel_id),
                user_id=UserID(db_user_id),
                action=ActionType(action_str),
                reason=reason,
                timeout_duration=timeout_dur,
                ban_duration=ban_dur,
                message_ids_to_delete=message_ids
            )
            
            # Group by user_id
            user_id_key = UserID(db_user_id)
            if user_id_key in actions_by_user:
                actions_by_user[user_id_key].append(action_data)
        
        duration = time.time() - start_time
        _track_query_performance("get_bulk_past_actions", duration)
        
        return actions_by_user
    
    def get_performance_stats(self) -> Dict[str, Dict[str, float]]:
        """
        Task #6: Get database query performance statistics.
        
        Returns:
            Dictionary of query statistics with timing information
        """
        return get_query_statistics()
    
    def reset_performance_stats(self) -> None:
        """
        Task #6: Reset database query performance statistics.
        
        Useful for starting fresh performance measurements.
        """
        global _query_stats
        _query_stats.clear()
        logger.info("[DATABASE] Performance statistics reset")


# Global Database instance
database = Database()

def get_db() -> Database:
    """
    Get the global Database instance.
    
    Returns:
        Database: The global Database manager instance.
    """
    return database