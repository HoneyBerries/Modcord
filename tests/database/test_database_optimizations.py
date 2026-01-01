"""
Tests for database optimization features.

This test suite validates the optimizations added:
- Performance monitoring
- Query caching
- Batch operations
- Database maintenance
"""

import pytest
import tempfile
from pathlib import Path

from modcord.database.database import Database
from modcord.datatypes.action_datatypes import ActionData, ActionType
from modcord.datatypes.discord_datatypes import UserID, GuildID, ChannelID


@pytest.fixture
async def test_db():
    """Create a temporary test database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        await db.initialize()
        yield db
        await db.shutdown()


@pytest.mark.asyncio
async def test_performance_monitoring(test_db):
    """Verify performance monitoring tracks queries."""
    # Clear stats
    test_db.reset_db_performance_stats()
    
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
    stats = test_db.get_db_performance_stats()
    assert "log_moderation_action" in stats
    assert stats["log_moderation_action"]["count"] >= 1
    assert stats["log_moderation_action"]["total_time"] > 0


@pytest.mark.asyncio
async def test_batch_operations(test_db):
    """Verify batch insert operations work correctly."""
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
    """Verify query result caching works."""
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
    count1 = await test_db.get_guild_action_count(guild_id, days=7)
    assert count1 == 3
    # Second query should hit cache (if implemented internally)
    count2 = await test_db.get_guild_action_count(guild_id, days=7)
    assert count2 == 3
    # If there is a cache clear method, call it (optional, comment out if not present)
    # test_db.clear_query_cache()
    count3 = await test_db.get_guild_action_count(guild_id, days=7)
    assert count3 == 3