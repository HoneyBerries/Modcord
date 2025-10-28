"""Tests for database module."""

import pytest
import tempfile
import os
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

from modcord.database.database import (
    init_database,
    get_connection,
    log_moderation_action,
    get_past_actions,
    DB_PATH,
)


@pytest.fixture
async def temp_db():
    """Create a temporary database for testing."""
    from modcord.database import database
    
    # Save original DB path
    original_path = database.DB_PATH
    
    # Create temporary database
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    temp_file.close()
    database.DB_PATH = Path(temp_file.name)
    
    # Initialize database
    await database.init_database()
    
    yield database.DB_PATH
    
    # Cleanup
    database.DB_PATH = original_path
    try:
        os.unlink(temp_file.name)
    except:
        pass


class TestInitDatabase:
    """Tests for init_database function."""

    async def test_init_creates_tables(self, temp_db):
        """Test that init_database creates required tables."""
        async with get_connection() as db:
            # Check guild_settings table
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='guild_settings'"
            )
            result = await cursor.fetchone()
            assert result is not None
            
            # Check channel_guidelines table
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='channel_guidelines'"
            )
            result = await cursor.fetchone()
            assert result is not None
            
            # Check schema_version table
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
            )
            result = await cursor.fetchone()
            assert result is not None

    async def test_init_creates_moderation_actions_table(self, temp_db):
        """Test that moderation_actions table is created."""
        async with get_connection() as db:
            # Create the table (since it's created on first log_moderation_action call)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS moderation_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    metadata TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()
            
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='moderation_actions'"
            )
            result = await cursor.fetchone()
            assert result is not None

    async def test_init_sets_schema_version(self, temp_db):
        """Test that schema version is set."""
        async with get_connection() as db:
            cursor = await db.execute("SELECT version FROM schema_version")
            result = await cursor.fetchone()
            assert result is not None
            assert result[0] == 1


class TestLogModerationAction:
    """Tests for log_moderation_action function."""

    async def test_log_simple_action(self, temp_db):
        """Test logging a simple moderation action."""
        # Create moderation_actions table
        async with get_connection() as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS moderation_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    metadata TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()
        
        await log_moderation_action(
            guild_id=123456,
            user_id="789012",
            action_type="warn",
            reason="Spam"
        )
        
        # Verify the action was logged
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT * FROM moderation_actions WHERE user_id = ?",
                ("789012",)
            )
            result = await cursor.fetchone()
            assert result is not None
            assert result[1] == 123456  # guild_id
            assert result[2] == "789012"  # user_id
            assert result[3] == "warn"  # action_type
            assert result[4] == "Spam"  # reason

    async def test_log_action_with_metadata(self, temp_db):
        """Test logging action with metadata."""
        # Create table
        async with get_connection() as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS moderation_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    metadata TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()
        
        metadata = {
            "ban_duration": 1440,
            "message_ids": ["msg1", "msg2"]
        }
        
        await log_moderation_action(
            guild_id=123456,
            user_id="789012",
            action_type="ban",
            reason="Serious violation",
            metadata=metadata
        )
        
        # Verify metadata was stored
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT metadata FROM moderation_actions WHERE action_type = ?",
                ("ban",)
            )
            result = await cursor.fetchone()
            assert result is not None
            stored_metadata = json.loads(result[0])
            assert stored_metadata["ban_duration"] == 1440
            assert stored_metadata["message_ids"] == ["msg1", "msg2"]

    async def test_log_action_without_metadata(self, temp_db):
        """Test logging action without metadata."""
        # Create table
        async with get_connection() as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS moderation_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    metadata TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()
        
        await log_moderation_action(
            guild_id=123456,
            user_id="789012",
            action_type="kick",
            reason="Rule violation",
            metadata=None
        )
        
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT metadata FROM moderation_actions WHERE action_type = ?",
                ("kick",)
            )
            result = await cursor.fetchone()
            assert result is not None
            assert result[0] is None


class TestGetPastActions:
    """Tests for get_past_actions function."""

    async def test_get_past_actions_within_window(self, temp_db):
        """Test retrieving past actions within time window."""
        # Create table and insert test data
        async with get_connection() as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS moderation_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    metadata TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Insert recent action
            recent_time = datetime.now(timezone.utc) - timedelta(minutes=5)
            await db.execute(
                """INSERT INTO moderation_actions 
                (guild_id, user_id, action_type, reason, timestamp) 
                VALUES (?, ?, ?, ?, ?)""",
                (123, "user1", "warn", "Test", recent_time.isoformat())
            )
            await db.commit()
        
        actions = await get_past_actions(123, "user1", lookback_minutes=10)
        
        assert len(actions) == 1
        assert actions[0]["action_type"] == "warn"
        assert actions[0]["reason"] == "Test"

    async def test_get_past_actions_outside_window(self, temp_db):
        """Test that old actions are not retrieved."""
        async with get_connection() as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS moderation_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    metadata TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Insert old action (2 hours ago)
            old_time = datetime.now(timezone.utc) - timedelta(hours=2)
            await db.execute(
                """INSERT INTO moderation_actions 
                (guild_id, user_id, action_type, reason, timestamp) 
                VALUES (?, ?, ?, ?, ?)""",
                (123, "user1", "warn", "Old", old_time.isoformat())
            )
            await db.commit()
        
        # Look back only 10 minutes
        actions = await get_past_actions(123, "user1", lookback_minutes=10)
        
        assert len(actions) == 0

    async def test_get_past_actions_multiple(self, temp_db):
        """Test retrieving multiple past actions."""
        async with get_connection() as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS moderation_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    metadata TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Insert multiple actions
            for i in range(3):
                time = datetime.now(timezone.utc) - timedelta(minutes=i)
                await db.execute(
                    """INSERT INTO moderation_actions 
                    (guild_id, user_id, action_type, reason, timestamp) 
                    VALUES (?, ?, ?, ?, ?)""",
                    (123, "user1", f"action{i}", f"Reason {i}", time.isoformat())
                )
            await db.commit()
        
        actions = await get_past_actions(123, "user1", lookback_minutes=60)
        
        assert len(actions) == 3

    async def test_get_past_actions_wrong_user(self, temp_db):
        """Test that actions for different user are not retrieved."""
        async with get_connection() as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS moderation_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    metadata TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            time = datetime.now(timezone.utc)
            await db.execute(
                """INSERT INTO moderation_actions 
                (guild_id, user_id, action_type, reason, timestamp) 
                VALUES (?, ?, ?, ?, ?)""",
                (123, "user2", "warn", "Test", time.isoformat())
            )
            await db.commit()
        
        actions = await get_past_actions(123, "user1", lookback_minutes=60)
        
        assert len(actions) == 0

    async def test_get_past_actions_with_metadata(self, temp_db):
        """Test retrieving actions with metadata."""
        async with get_connection() as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS moderation_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    metadata TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            metadata = {"duration": 60}
            time = datetime.now(timezone.utc)
            await db.execute(
                """INSERT INTO moderation_actions 
                (guild_id, user_id, action_type, reason, metadata, timestamp) 
                VALUES (?, ?, ?, ?, ?, ?)""",
                (123, "user1", "timeout", "Test", json.dumps(metadata), time.isoformat())
            )
            await db.commit()
        
        actions = await get_past_actions(123, "user1", lookback_minutes=60)
        
        assert len(actions) == 1
        assert actions[0]["metadata"]["duration"] == 60
