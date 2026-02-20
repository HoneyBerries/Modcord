"""
Database coordinator for Modcord.

All SQL I/O flows through the single long-lived ``db_connection``
singleton (see db_connection.py).  This module is responsible for:
- Opening / closing that connection at the right lifecycle points
- Initializing the schema on first run
- Exposing high-level helpers (log action, query history, etc.)

Connection model
----------------
``db_connection.open()`` is called once at startup.  After that every
repository and storage class borrows the same live connection:
  - Reads  → ``db_connection.connection`` (WAL; fully concurrent)
  - Writes → ``async with db_connection.transaction()`` (serialized)

This eliminates the per-operation connect/disconnect overhead and
keeps the SQLite page cache warm for the entire bot lifetime.
"""

from __future__ import annotations

from pathlib import Path

from modcord.database.db_connection import db_connection
from modcord.database.db_schema import SchemaManager
from modcord.util.logger import get_logger

logger = get_logger("database")

DB_PATH = Path("./data/app.db").resolve()


class Database:
    """
    Central database coordinator.

    Lifecycle
    ---------
    1. ``await database.initialize()`` — opens the connection, creates schema.
    2. Use the helper methods throughout the bot lifetime.
    3. ``await database.shutdown()`` — flushes WAL and closes the connection.
    """

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self._initialized = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> bool:
        """
        Open the database connection and create the schema.

        Safe to call multiple times — subsequent calls are no-ops.

        Returns:
            True on success, False if an error occurred.
        """
        if self._initialized:
            logger.debug("[DATABASE] Already initialized, skipping")
            return True

        try:
            await db_connection.open(self.db_path)

            async with db_connection.transaction() as conn:
                await SchemaManager.initialize_schema(conn)

            self._initialized = True
            logger.info("[DATABASE] Ready at %s", self.db_path)
            return True

        except Exception as e:
            logger.error("[DATABASE] Initialization failed, %s", e, exc_info=True)
            return False

    async def shutdown(self) -> None:
        """
        Flush the WAL and close the connection cleanly.

        Should be called when the bot is shutting down.
        """
        if not self._initialized:
            return

        self._initialized = False
        await db_connection.close()
        logger.info("[DATABASE] Database Shutdown completed successfully")

# Global singleton
database = Database()