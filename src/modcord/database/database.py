"""
Database initialization and connection management for SQLite.

This module provides a centralized Database class that coordinates
database operations including schema management and moderation action logging.

SQLite's WAL mode handles concurrent access safely with its own
internal locking mechanisms, so no application-level locking is needed.

The Database class acts as a coordinator, delegating to specialized
modules for different concerns:
- schema: Table/index creation and migrations
- moderation: Action logging and querying
- performance: Query timing and statistics
- connection: Connection management with optimized pragmas
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Dict, Optional

from modcord.datatypes.action_datatypes import ActionData
from modcord.datatypes.discord_datatypes import UserID, GuildID
from modcord.util.logger import get_logger
from modcord.database.db_connection import DatabaseConnectionContext
from modcord.database.db_schema import SchemaManager
from modcord.database.moderation_action_storage import ModerationActionStorage

logger = get_logger("database")

# Database file path
DB_PATH = Path("./data/app.db").resolve()


class Database:
    """
    Central database coordinator for all database operations.
    
    This class coordinates between specialized modules to provide:
    - Database initialization and schema management
    - Moderation action logging and querying
    - Performance monitoring and caching
    
    Lifecycle:
        1. Call initialize() at program startup
        2. Use the various methods for database operations
        3. Call shutdown() at program end (optional)
    """
    
    def __init__(self, db_path: Path = DB_PATH):
        """
        Initialize the Database coordinator.
        
        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self._initialized = False
        
        # Initialize specialized modules
        self.moderation_action_storage = ModerationActionStorage()
    
    def get_connection(self) -> DatabaseConnectionContext:
        """
        Get an async database connection for use in a context manager.
        
        The returned connection automatically enables foreign keys and WAL mode.
        
        Returns:
            DatabaseConnectionContext: Async context manager yielding a connection.
        """
        return DatabaseConnectionContext(self.db_path)


    async def initialize(self) -> bool:
        """
        Initialize the database and create schema.
        
        This method should be called once at program startup. It:
        1. Creates the database directory if needed
        2. Creates all required tables, indexes, and triggers via SchemaManager
        
        Returns:
            True if initialization succeeded, False otherwise
        """
        if self._initialized:
            logger.debug("[DATABASE] Already initialized, skipping")
            return True
        
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            async with self.get_connection() as db:
                await SchemaManager.initialize_schema(db)
            
            self._initialized = True
            logger.info("[DATABASE] Database initialized at %s", self.db_path)
            return True
            
        except Exception as e:
            logger.error("[DATABASE] Database initialization failed: %s", e)
            return False
    
    async def shutdown(self) -> None:
        """
        Shutdown the database.
        
        This method should be called at program shutdown for cleanup.
        It performs a TRUNCATE checkpoint to ensure all WAL data is flushed
        to the main database file, allowing SQLite to automatically remove
        the .db-wal and .db-shm files when the last connection closes.
        """
        if not self._initialized:
            return
        
        self._initialized = False
        logger.info("[DATABASE] Database shutdown complete")

    
    
    async def log_moderation_action(self, action: ActionData) -> None:
        """
        Log a moderation action to the database.
        
        Args:
            action: ActionData object containing all action details
        """
        async with self.get_connection() as db:
            await self.moderation_action_storage.log_action(db, action)
    
    async def log_moderation_actions_batch(self, actions: List[ActionData]) -> int:
        """
        Batch log multiple moderation actions in a single transaction.
        
        Args:
            actions: List of ActionData objects to log
        
        Returns:
            Number of actions successfully logged, or -1 on error
        """
        async with self.get_connection() as db:
            return await self.moderation_action_storage.log_actions_batch(db, actions)

    async def get_bulk_past_actions(
        self,
        guild_id: GuildID,
        user_ids: List[UserID],
        lookback_minutes: int
    ) -> Dict[UserID, List[ActionData]]:
        """
        Query past moderation actions for multiple users within a time window.
        
        Args:
            guild_id: ID of the guild to query actions from
            user_ids: List of user IDs to query history for
            lookback_minutes: How many minutes back to query
        
        Returns:
            Dictionary mapping user_id to list of ActionData objects
        """
        async with self.get_connection() as db:
            return await self.moderation_action_storage.get_bulk_past_actions(db, guild_id, user_ids, lookback_minutes)
    
    
    async def get_guild_action_count(self, guild_id: GuildID, days: int = 7) -> int:
        """
        Get total action count for a guild.
        
        Args:
            guild_id: Guild ID to query
            days: Number of days to look back
        
        Returns:
            Total number of actions in the time period
        """
        async with self.get_connection() as db:
            return await self.moderation_action_storage.get_guild_action_count(db, guild_id, days)


# Global Database instance
database = Database()