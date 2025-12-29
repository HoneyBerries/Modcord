"""
Moderation action logging and querying operations.

Handles storage and retrieval of moderation actions from the database
with performance optimizations for batch operations and bulk queries.
"""

import time
from typing import List, Dict
from datetime import datetime, timedelta, timezone

import aiosqlite

from modcord.datatypes.action_datatypes import ActionData, ActionType
from modcord.datatypes.discord_datatypes import UserID, GuildID, MessageID, ChannelID
from modcord.database.db_perf_mon import DatabasePerformanceMonitor
from modcord.database.db_cache import DatabaseQueryCache
from modcord.util.logger import get_logger

logger = get_logger("database_moderation")


class ModerationActions:
    """Handles moderation action logging and querying."""
    
    def __init__(self, performance: DatabasePerformanceMonitor, cache: DatabaseQueryCache):
        """
        Initialize moderation actions handler.
        
        Args:
            performance: Performance monitor for tracking query times
            cache: Query cache for frequently accessed data
        """
        self._performance = performance
        self._cache = cache
    
    async def log_action(self, db: aiosqlite.Connection, action: ActionData) -> None:
        """
        Log a single moderation action to the database.
        
        Args:
            db: Open database connection
            action: ActionData object containing all action details
        """
        start_time = time.time()
        
        message_ids = ",".join(str(mid.to_int()) for mid in (action.message_ids_to_delete or []))
        
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
        self._performance.track("log_moderation_action", duration)
        self._cache.invalidate(f"action_count:{action.guild_id.to_int()}")
        
        logger.debug(
            "[MODERATION] Logged action: %s on user %s in guild %s channel %s",
            action.action.value,
            action.user_id,
            action.guild_id,
            action.channel_id
        )
    
    async def log_actions_batch(self, db: aiosqlite.Connection, actions: List[ActionData]) -> int:
        """
        Batch log multiple moderation actions in a single transaction.
        
        This is more efficient than calling log_action() multiple times
        as it uses a single database transaction with executemany.
        
        Args:
            db: Open database connection
            actions: List of ActionData objects to log
        
        Returns:
            Number of actions successfully logged, or -1 on error
        """
        if not actions:
            return 0
        
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
            
            await db.executemany(
                """
                INSERT INTO moderation_actions (guild_id, channel_id, user_id, action, reason, timeout_duration, ban_duration, message_ids)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                batch_data
            )
            await db.commit()
            
            duration = time.time() - start_time
            self._performance.track("log_moderation_actions_batch", duration)
            
            # Invalidate cache for affected guilds
            guild_ids_affected = set(action.guild_id.to_int() for action in actions)
            for guild_id in guild_ids_affected:
                self._cache.invalidate(f"action_count:{guild_id}")
            
            logger.debug(
                "[MODERATION] Batch logged %d actions in %.2fms",
                len(actions), duration * 1000
            )
            return len(actions)
            
        except Exception as e:
            logger.error("[MODERATION] Batch log failed: %s", e)
            return -1
    
    async def get_bulk_past_actions(
        self,
        db: aiosqlite.Connection,
        guild_id: GuildID,
        user_ids: List[UserID],
        lookback_minutes: int
    ) -> Dict[UserID, List[ActionData]]:
        """
        Query past moderation actions for multiple users within a time window.
        
        This is more efficient than querying per user as it makes
        a single database query with IN clause.
        
        Args:
            db: Open database connection
            guild_id: ID of the guild to query actions from
            user_ids: List of user IDs to query history for
            lookback_minutes: How many minutes back to query
        
        Returns:
            Dictionary mapping user_id to list of ActionData objects
        """
        if not user_ids:
            return {}
        
        start_time = time.time()
        
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)
        guild_id_int = guild_id.to_int() if isinstance(guild_id, GuildID) else guild_id
        
        # Create placeholders for IN clause
        user_id_strs = [str(user_id) for user_id in user_ids]
        placeholders = ','.join('?' * len(user_id_strs))
        
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
        self._performance.track("get_bulk_past_actions", duration)
        
        return actions_by_user
    
    async def get_guild_action_count(
        self,
        db: aiosqlite.Connection,
        guild_id: GuildID,
        days: int = 7
    ) -> int:
        """
        Get total action count for a guild with caching.
        
        Results are cached to reduce database queries for frequently
        accessed guild statistics.
        
        Args:
            db: Open database connection
            guild_id: Guild ID to query
            days: Number of days to look back
        
        Returns:
            Total number of actions in the time period
        """
        cache_key = f"action_count:{guild_id.to_int()}:{days}"
        
        # Check cache first
        cached_result = self._cache.get(cache_key)
        if cached_result is not None:
            return cached_result
        
        # Query database
        start_time = time.time()
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        cursor = await db.execute(
            "SELECT COUNT(*) FROM moderation_actions WHERE guild_id = ? AND timestamp >= ?",
            (guild_id.to_int(), cutoff_date.isoformat())
        )
        row = await cursor.fetchone()
        count = row[0] if row else 0
        
        duration = time.time() - start_time
        self._performance.track("get_guild_action_count", duration)
        
        # Cache the result
        self._cache.set(cache_key, count)
        
        return count
