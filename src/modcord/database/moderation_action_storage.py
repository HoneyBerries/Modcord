"""
Moderation action logging and querying operations.

Handles storage and retrieval of moderation actions from the database
with performance optimizations for batch operations and bulk queries.
"""

from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone

import aiosqlite

from modcord.datatypes.action_datatypes import ActionData, ActionType
from modcord.datatypes.discord_datatypes import UserID, GuildID, MessageID, ChannelID
from modcord.util.logger import get_logger

logger = get_logger("DB MODERATION ACTIONS")


class ModerationActionStorage:
    """Handles moderation action logging and querying."""
    def __init__(self):
        pass
    
    async def log_action(self, db: aiosqlite.Connection, action: ActionData) -> None:
        """
        Log a single moderation action to the database.
        
        Args:
            db: Open database connection
            action: ActionData object containing all action details
        """
        # Performance monitoring removed
        
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
        
        
        logger.debug(
            "Logged action: %s on user %s in guild %s channel %s",
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
        
        # Performance monitoring removed
        
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
            
            
            logger.debug(
                "[MODERATION] Batch logged %d actions",
                len(actions)
            )
            return len(actions)
            
        except Exception as e:
            logger.error("Batch log failed: %s", e)
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
        
        # Performance monitoring removed
        
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
        
        
        return actions_by_user
    
    async def get_guild_action_count(
        self,
        db: aiosqlite.Connection,
        guild_id: GuildID,
        days: int = 7
    ) -> int:
        """
        Get total action count for a guild.
        
        Args:
            db: Open database connection
            guild_id: Guild ID to query
            days: Number of days to look back
        
        Returns:
            Total number of actions in the time period
        """
        # Always query the database directly; SQLite pages are already cached
        # Performance monitoring removed
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        cursor = await db.execute(
            "SELECT COUNT(*) FROM moderation_actions WHERE guild_id = ? AND timestamp >= ?",
            (guild_id.to_int(), cutoff_date.isoformat())
        )
        row = await cursor.fetchone()
        count = row[0] if row else 0
        
        return count
    
    async def save_temp_ban(self, db: aiosqlite.Connection, guild_id: int, user_id: int, unban_at: int, reason: str) -> None:
        """
        Save or update a temporary ban record.
        
        Uses INSERT OR REPLACE to handle duplicate bans automatically.
        If a ban already exists for this guild_id + user_id, it updates the unban_at and reason.
        
        Args:
            db: Open database connection
            guild_id: Discord guild ID
            user_id: Discord user ID
            unban_at: Unix timestamp when the ban should expire
            reason: Reason for the ban
        """
        await db.execute(
            """INSERT OR REPLACE INTO bans (guild_id, user_id, unban_at, reason) VALUES (?, ?, ?, ?)""",
            (guild_id, str(user_id), unban_at, reason)
        )
        await db.commit()
        logger.debug(f"Saved temporary ban for user {user_id} in guild {guild_id}, unban at {unban_at}")
    

    async def get_expired_bans(self, db: aiosqlite.Connection, current_time: int) -> List[Dict[str, Any]]:
        """
        Retrieve all bans that have expired (unban_at <= current_time).
        
        Args:
            db: Open database connection
            current_time: Unix timestamp of current time
        
        Returns:
            List of dictionaries with keys: id, guild_id, user_id, unban_at, reason
        """
        cursor = await db.execute(
            """SELECT id, guild_id, user_id, unban_at, reason FROM bans WHERE unban_at <= ?""",
            (current_time,)
        )
        rows = await cursor.fetchall()
        
        bans = [
            {
                "id": int(row[0]),
                "guild_id": int(row[1]),
                "user_id": int(row[2]),
                "unban_at": int(row[3]),
                "reason": str(row[4])
            }
            for row in rows
        ]
        
        logger.debug(f"Found {len(bans)} expired bans at time {current_time}")
        return bans
    

    
    async def delete_ban(self, db: aiosqlite.Connection, guild_id: int, user_id: int) -> None:
        """
        Delete a ban record from the database.
        
        Removes the ban entry completely after successful unban.
        
        Args:
            db: Open database connection
            guild_id: Discord guild ID
            user_id: Discord user ID
        """
        await db.execute(
            """DELETE FROM bans WHERE guild_id = ? AND user_id = ?""",
            (guild_id, str(user_id))
        )
        await db.commit()
        logger.debug(f"Deleted ban record for user {user_id} in guild {guild_id}")