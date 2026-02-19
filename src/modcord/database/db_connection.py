"""
Database connection management — singleton connection model.

Design rationale
----------------
SQLite performs best with a **single long-lived connection** rather than
opening/closing a connection per operation:
  - Avoids repeated handshake and pragma setup overhead
  - Keeps the 64 MB page cache warm across operations
  - WAL mode allows one writer + unlimited concurrent readers safely

Concurrency model
-----------------
SQLite is inherently single-writer.  We enforce this at the application
layer with a write semaphore (``_write_sem``) so async tasks queue up
without fighting SQLite's busy-timeout.

Reads are always safe to run concurrently in WAL mode — no semaphore
needed there.

Usage
-----
    # One-time setup, normally called inside Database.initialize():
    await db_connection.open(DB_PATH)

    # Long-lived reads — share the connection directly
    conn = db_connection.connection
    rows = await conn.execute("SELECT ...")

    # Atomic writes — serialised, auto-rollback on error
    async with db_connection.transaction() as conn:
        await conn.execute("INSERT ...")
        await conn.execute("UPDATE ...")
        # commits automatically on clean exit, rolls back on exception

    # Shutdown
    await db_connection.close()
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import aiosqlite

from modcord.util.logger import get_logger

logger = get_logger("database_connection")

# ── Pragmas applied once when the connection is opened ──────────────────────
_PRAGMAS = [
    "PRAGMA journal_mode = WAL",
    "PRAGMA foreign_keys = ON",
    "PRAGMA synchronous = NORMAL",    # safe with WAL; faster than FULL
    "PRAGMA cache_size = 262144",     # 256 MB page cache
    "PRAGMA temp_store = MEMORY",
    "PRAGMA mmap_size = 268435456",   # 256 MB memory-mapped I/O
    "PRAGMA wal_autocheckpoint = 1000",  # checkpoint every ~1 000 pages
]


class ConnectionManager:
    """
    Singleton wrapper around a single aiosqlite connection.

    One connection is opened for the entire bot lifecycle.  All
    repositories and services call through this object instead of
    opening their own connections.

    Thread / task safety
    --------------------
    * Reads  — call ``connection`` directly; WAL allows concurrent reads.
    * Writes — use ``async with transaction()``; writes are serialised by
      ``_write_sem`` so no two coroutines write at the same time.
    """

    def __init__(self) -> None:
        self._conn: aiosqlite.Connection | None = None
        self._write_sem = asyncio.Semaphore(1)   # one writer at a time
        self._path: Path | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def open(self, path: Path) -> None:
        """
        Open the database and apply performance pragmas.

        Should be called **once** during bot startup, before any
        repository or service is used.

        Args:
            path: Path to the SQLite database file.
        """
        if self._conn is not None:
            logger.warning("[DB CONNECTION] open() called but connection already exists — ignoring")
            return

        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = await aiosqlite.connect(path)
        self._conn.row_factory = aiosqlite.Row  # rows are dict-like

        for pragma in _PRAGMAS:
            await self._conn.execute(pragma)
        await self._conn.commit()

        logger.info("[DB CONNECTION] Opened connection to %s", path)

    async def close(self) -> None:
        """
        Flush WAL and close the connection.

        Should be called during bot shutdown.
        """
        if self._conn is None:
            return

        try:
            # Flush all WAL pages to the main DB file
            await self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            await self._conn.commit()
        except Exception:
            logger.exception("[DB CONNECTION] WAL checkpoint failed during close")
        finally:
            await self._conn.close()
            self._conn = None
            logger.info("[DB CONNECTION] Connection closed")

    # ------------------------------------------------------------------
    # Connection access (reads)
    # ------------------------------------------------------------------

    @property
    def connection(self) -> aiosqlite.Connection:
        """
        The raw aiosqlite connection for read operations.

        Raises:
            RuntimeError: If the connection has not been opened yet.
        """
        if self._conn is None:
            raise RuntimeError(
                "DatabaseConnectionManager: connection is not open. "
                "Call await db_connection.open(path) at startup."
            )
        return self._conn

    # ------------------------------------------------------------------
    # Transaction context (writes)
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[aiosqlite.Connection]:
        """
        Async context manager that provides a serialised write transaction.

        * Acquires the write semaphore so only one transaction is active at
          a time (SQLite's single-writer constraint).
        * Commits automatically on clean exit.
        * Rolls back automatically if an exception is raised.

        Usage::

            async with db_connection.transaction() as conn:
                await conn.execute("INSERT INTO ...")
                await conn.execute("UPDATE ...")
                # ← commits here

        Raises:
            RuntimeError: If the connection is not open.
        """
        conn = self.connection           # raises if not open

        async with self._write_sem:      # serialise writers
            try:
                yield conn
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise

    # ------------------------------------------------------------------
    # Convenience: read-only cursor
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def read(self) -> AsyncIterator[aiosqlite.Connection]:
        """
        Async context manager for explicit read operations.

        Reads in WAL mode are always non-blocking — this is just a
        convenience wrapper that makes ``async with db_connection.read()``
        look symmetrical with ``async with db_connection.transaction()``.
        No semaphore is acquired.

        Usage::

            async with db_connection.read() as conn:
                cursor = await conn.execute("SELECT * FROM guild_settings")
                rows = await cursor.fetchall()
        """
        yield self.connection


# Module-level singleton
db_connection = ConnectionManager()
