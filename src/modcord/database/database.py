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
from typing import Dict, List

from modcord.database.db_connection import db_connection
from modcord.database.db_schema import SchemaManager
from modcord.database.moderation_action_storage import ModerationActionStorage
from modcord.datatypes.action_datatypes import ActionData
from modcord.datatypes.discord_datatypes import GuildID, UserID
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
        self.moderation_action_storage = ModerationActionStorage()

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

        except Exception:
            logger.exception("[DATABASE] Initialization failed")
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
        logger.info("[DATABASE] Shutdown complete")

    # ------------------------------------------------------------------
    # Moderation action helpers
    # ------------------------------------------------------------------

    async def log_moderation_action(self, action: ActionData) -> None:
        """
        Persist a single moderation action.

        Args:
            action: ActionData to log.
        """
        async with db_connection.transaction() as conn:
            await self.moderation_action_storage.log_action(conn, action)

    async def log_moderation_actions_batch(self, actions: List[ActionData]) -> int:
        """
        Persist multiple moderation actions in a single transaction.

        Args:
            actions: List of ActionData objects to log.

        Returns:
            Number of actions successfully logged, or -1 on error.
        """
        async with db_connection.transaction() as conn:
            return await self.moderation_action_storage.log_actions_batch(conn, actions)

    async def get_bulk_past_actions(
        self,
        guild_id: GuildID,
        user_ids: List[UserID],
        lookback_minutes: int,
    ) -> Dict[UserID, List[ActionData]]:
        """
        Query past moderation actions for multiple users within a time window.

        Args:
            guild_id: Guild to query.
            user_ids: Users to look up.
            lookback_minutes: How far back to search.

        Returns:
            Mapping of UserID → list of ActionData.
        """
        async with db_connection.read() as conn:
            return await self.moderation_action_storage.get_bulk_past_actions(
                conn, guild_id, user_ids, lookback_minutes
            )

    async def get_guild_action_count(self, guild_id: GuildID, days: int = 7) -> int:
        """
        Get the number of moderation actions logged for a guild.

        Args:
            guild_id: Guild to query.
            days: Number of days to look back.

        Returns:
            Total action count.
        """
        async with db_connection.read() as conn:
            return await self.moderation_action_storage.get_guild_action_count(
                conn, guild_id, days
            )


# Global singleton
database = Database()