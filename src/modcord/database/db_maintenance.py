"""
Database maintenance operations.

Provides utilities for database optimization, cleanup, and health monitoring
including VACUUM, ANALYZE, and old data cleanup operations.
"""

import time
from datetime import datetime, timedelta, timezone

import aiosqlite

from modcord.database.db_perf_mon import DatabasePerformanceMonitor
from modcord.util.logger import get_logger

logger = get_logger("database_maintenance")


class MaintenanceOperations:
    """Handles database maintenance and optimization operations."""
    
    def __init__(self, performance: DatabasePerformanceMonitor):
        """
        Initialize maintenance operations handler.
        
        Args:
            performance: Performance monitor for tracking operation times
        """
        self._performance = performance
    
    async def vacuum(self, db: aiosqlite.Connection) -> bool:
        """
        Perform database vacuum to reclaim space and optimize storage.
        
        Should be called periodically during maintenance windows.
        
        Args:
            db: Open database connection
        
        Returns:
            True if vacuum succeeded, False otherwise
        """
        try:
            logger.info("[MAINTENANCE] Starting VACUUM operation")
            start_time = time.time()
            await db.execute("VACUUM")
            duration = time.time() - start_time
            logger.info("[MAINTENANCE] VACUUM completed in %.2f seconds", duration)
            self._performance.track("VACUUM", duration)
            return True
        except Exception as e:
            logger.error("[MAINTENANCE] VACUUM failed: %s", e)
            return False
    
    async def analyze(self, db: aiosqlite.Connection) -> bool:
        """
        Update database statistics for query optimizer.
        
        Should be called periodically to maintain optimal query performance.
        
        Args:
            db: Open database connection
        
        Returns:
            True if analyze succeeded, False otherwise
        """
        try:
            logger.info("[MAINTENANCE] Starting ANALYZE operation")
            start_time = time.time()
            await db.execute("ANALYZE")
            duration = time.time() - start_time
            logger.info("[MAINTENANCE] ANALYZE completed in %.2f seconds", duration)
            self._performance.track("ANALYZE", duration)
            return True
        except Exception as e:
            logger.error("[MAINTENANCE] ANALYZE failed: %s", e)
            return False
    
    async def cleanup_old_actions(
        self,
        db: aiosqlite.Connection,
        days_to_keep: int = 30
    ) -> int:
        """
        Clean up old moderation actions to reduce database size.
        
        Args:
            db: Open database connection
            days_to_keep: Number of days of history to retain (default: 30)
        
        Returns:
            Number of records deleted, or -1 on error
        """
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
            cursor = await db.execute(
                "DELETE FROM moderation_actions WHERE timestamp < ?",
                (cutoff_date.isoformat(),)
            )
            await db.commit()
            deleted_count = cursor.rowcount
            logger.info(
                "[MAINTENANCE] Cleaned up %d moderation actions older than %d days",
                deleted_count, days_to_keep
            )
            return deleted_count
        except Exception as e:
            logger.error("[MAINTENANCE] Cleanup failed: %s", e)
            return -1
