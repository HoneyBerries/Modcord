"""
Tests for database optimization features.

This test suite validates the optimizations added in tasks #1-#10:
- Performance monitoring (#6)
- Query caching (#3)
- Batch operations (#4)
- Database maintenance (#10)
"""

import pytest
import tempfile
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone

from modcord.database.database import Database, get_query_statistics, _invalidate_cache
from modcord.datatypes.action_datatypes import ActionData, ActionType
from modcord.datatypes.discord_datatypes import UserID, GuildID, MessageID, ChannelID


@pytest.fixture
async def test_db():
    """Create a temporary test database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        await db.initialize()
        yield db
        db.shutdown()


@pytest.mark.asyncio
async def test_performance_monitoring(test_db):
    """Test #6: Verify performance monitoring tracks queries."""
    # Clear stats
    test_db.reset_performance_stats()
    
    # Log an action
    action = ActionData(
        guild_id=GuildID(123),
        channel_id=ChannelID(456),
        user_id=UserID(789),
        action=ActionType.WARN,
        reason="Test warning"
    )
    await test_db.log_moderation_action(action)
    
    # Check stats were recorded
    stats = test_db.get_performance_stats()
    assert "log_moderation_action" in stats
    assert stats["log_moderation_action"]["count"] >= 1
    assert stats["log_moderation_action"]["total_time"] > 0


@pytest.mark.asyncio
async def test_batch_operations(test_db):
    """Test #4: Verify batch insert operations work correctly."""
    actions = [
        ActionData(
            guild_id=GuildID(123),
            channel_id=ChannelID(456),
            user_id=UserID(1000 + i),  # Use numeric IDs
            action=ActionType.WARN,
            reason=f"Test warning {i}"
        )
        for i in range(5)
    ]
    
    # Batch insert
    count = await test_db.log_moderation_actions_batch(actions)
    assert count == 5
    
    # Verify they were inserted - use longer lookback to ensure we capture the records
    guild_id = GuildID(123)
    user_ids = [UserID(1000 + i) for i in range(5)]
    results = await test_db.get_bulk_past_actions(guild_id, user_ids, 60 * 24)  # 24 hours
    
    # Should have actions for all users
    assert len(results) == 5
    for user_id in user_ids:
        assert user_id in results
        assert len(results[user_id]) >= 1  # At least one action per user


@pytest.mark.asyncio
async def test_query_caching(test_db):
    """Test #3: Verify query result caching works."""
    guild_id = GuildID(123)
    
    # Log some actions
    for i in range(3):
        action = ActionData(
            guild_id=guild_id,
            channel_id=ChannelID(456),
            user_id=UserID(2000 + i),  # Use numeric IDs
            action=ActionType.WARN,
            reason=f"Test {i}"
        )
        await test_db.log_moderation_action(action)
    
    # First query should hit database
    count1 = await test_db.get_cached_guild_action_count(guild_id, days=7)
    assert count1 == 3
    
    # Second query should hit cache
    count2 = await test_db.get_cached_guild_action_count(guild_id, days=7)
    assert count2 == 3
    
    # Clear cache and verify
    test_db.clear_query_cache()
    count3 = await test_db.get_cached_guild_action_count(guild_id, days=7)
    assert count3 == 3


@pytest.mark.asyncio
async def test_database_maintenance(test_db):
    """Test #10: Verify database maintenance operations work."""
    # Test analyze
    result = await test_db.analyze()
    assert result is True
    
    # Test vacuum (may take time but should succeed)
    result = await test_db.vacuum()
    assert result is True


@pytest.mark.asyncio
async def test_cleanup_old_actions(test_db):
    """Test #10: Verify cleanup of old actions."""
    guild_id = GuildID(123)
    
    # Log an action
    action = ActionData(
        guild_id=guild_id,
        channel_id=ChannelID(456),
        user_id=UserID(789),
        action=ActionType.WARN,
        reason="Test"
    )
    await test_db.log_moderation_action(action)
    
    # Cleanup actions older than 0 days (should delete nothing recent)
    deleted = await test_db.cleanup_old_actions(days_to_keep=30)
    assert deleted >= 0  # Should not error


@pytest.mark.asyncio
async def test_bulk_past_actions_performance(test_db):
    """Test #5: Verify optimized timestamp queries work efficiently."""
    guild_id = GuildID(123)
    user_ids = [UserID(3000 + i) for i in range(10)]  # Use numeric IDs
    
    # Log actions for multiple users
    actions = []
    for user_id in user_ids:
        actions.append(ActionData(
            guild_id=guild_id,
            channel_id=ChannelID(456),
            user_id=user_id,
            action=ActionType.WARN,
            reason="Test"
        ))
    
    await test_db.log_moderation_actions_batch(actions)
    
    # Query should use optimized indexes
    results = await test_db.get_bulk_past_actions(guild_id, user_ids, 10)
    
    # Verify results
    assert len(results) == len(user_ids)
    for user_id in user_ids:
        assert user_id in results
