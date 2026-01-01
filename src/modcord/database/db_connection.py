"""
Database connection management.

Provides async context managers for database connections with
optimized SQLite pragmas for performance.

WAL (Write-Ahead Logging) Mode:
    SQLite WAL mode creates two additional files:
    - .db-wal: Contains recent uncommitted changes
    - .db-shm: Shared memory index for the WAL file
    
    These files are automatically managed by SQLite:
    - Checkpointed automatically when WAL grows large
    - Removed automatically when last connection closes cleanly
    - Manual checkpoint available via maintenance.checkpoint_wal()
"""

from pathlib import Path
import aiosqlite

from modcord.util.logger import get_logger

logger = get_logger("database_connection")


class DatabaseConnectionContext:
    """
    Async context manager for database connections.
    
    Automatically applies optimized SQLite pragmas when opening
    a connection to ensure consistent performance settings.
    """
    
    def __init__(self, db_path: Path):
        """
        Initialize connection context.
        
        Args:
            db_path: Path to the SQLite database file
        """
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None
    
    async def __aenter__(self) -> aiosqlite.Connection:
        """
        Open database connection with optimized pragmas.
        
        Returns:
            Open aiosqlite connection
        """
        self._conn = await aiosqlite.connect(self._db_path)
        
        # Apply optimized pragmas
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.execute("PRAGMA journal_mode = WAL")
        await self._conn.execute("PRAGMA synchronous = NORMAL")
        await self._conn.execute("PRAGMA cache_size = -64000")  # 64MB cache
        await self._conn.execute("PRAGMA temp_store = MEMORY")
        await self._conn.execute("PRAGMA mmap_size = 268435456")  # 256MB mmap
        
        return self._conn
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close the database connection."""
        if self._conn:
            await self._conn.close()