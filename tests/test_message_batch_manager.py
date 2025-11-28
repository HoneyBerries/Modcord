"""Tests for message_batch_manager module."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from modcord.moderation.message_batch_manager import MessageBatchManager
from modcord.moderation.moderation_datatypes import (
    ModerationMessage,
    ModerationUser,
)


class TestMessageBatchManager:
    """Tests for MessageBatchManager class."""

    def test_initialization(self):
        """Test MessageBatchManager initialization."""
        manager = MessageBatchManager()
        assert manager._channel_message_batches is not None
        assert manager._batch_lock is not None
        assert manager._global_batch_timer is None
        assert manager._batch_processing_callback is None
        assert manager._bot_instance is None
        assert manager._history_fetcher is None

    def test_set_bot_instance(self):
        """Test set_bot_instance configures bot and history fetcher."""
        manager = MessageBatchManager()
        mock_bot = Mock()
        
        manager.set_bot_instance(mock_bot)
        
        assert manager._bot_instance is mock_bot
        assert manager._history_fetcher is not None

    def test_set_batch_processing_callback(self):
        """Test set_batch_processing_callback stores callback."""
        manager = MessageBatchManager()
        mock_callback = AsyncMock()
        
        manager.set_batch_processing_callback(mock_callback)
        
        assert manager._batch_processing_callback is mock_callback

    @pytest.mark.asyncio
    async def test_add_message_to_batch(self):
        """Test add_message_to_batch queues a message."""
        manager = MessageBatchManager()
        
        timestamp = datetime.now(timezone.utc).isoformat()
        msg = ModerationMessage(
            message_id="123",
            user_id="456",
            content="Test message",
            timestamp=timestamp,
            guild_id=789,
            channel_id=111
        )
        
        await manager.add_message_to_batch(111, msg)
        
        assert 111 in manager._channel_message_batches
        assert len(manager._channel_message_batches[111]) == 1
        assert manager._channel_message_batches[111][0].message_id == "123"

    @pytest.mark.asyncio
    async def test_add_message_to_batch_starts_timer(self):
        """Test add_message_to_batch starts global batch timer."""
        manager = MessageBatchManager()
        
        timestamp = datetime.now(timezone.utc).isoformat()
        msg = ModerationMessage(
            message_id="123",
            user_id="456",
            content="Test",
            timestamp=timestamp,
            guild_id=789,
            channel_id=111
        )
        
        await manager.add_message_to_batch(111, msg)
        
        assert manager._global_batch_timer is not None
        assert not manager._global_batch_timer.done()
        
        # Cleanup
        if manager._global_batch_timer:
            manager._global_batch_timer.cancel()

    @pytest.mark.asyncio
    async def test_remove_message_from_batch(self):
        """Test remove_message_from_batch removes a message."""
        manager = MessageBatchManager()
        
        timestamp = datetime.now(timezone.utc).isoformat()
        msg = ModerationMessage(
            message_id="123",
            user_id="456",
            content="Test",
            timestamp=timestamp,
            guild_id=789,
            channel_id=111
        )
        
        await manager.add_message_to_batch(111, msg)
        assert len(manager._channel_message_batches[111]) == 1
        
        await manager.remove_message_from_batch(111, "123")
        assert len(manager._channel_message_batches[111]) == 0
        
        # Cleanup timer
        if manager._global_batch_timer:
            manager._global_batch_timer.cancel()

    @pytest.mark.asyncio
    async def test_remove_message_from_batch_nonexistent(self):
        """Test remove_message_from_batch handles nonexistent messages."""
        manager = MessageBatchManager()
        
        # Should not raise error
        await manager.remove_message_from_batch(111, "nonexistent")

    @pytest.mark.asyncio
    async def test_update_message_in_batch(self):
        """Test update_message_in_batch updates message content."""
        manager = MessageBatchManager()
        
        timestamp = datetime.now(timezone.utc).isoformat()
        msg1 = ModerationMessage(
            message_id="123",
            user_id="456",
            content="Original",
            timestamp=timestamp,
            guild_id=789,
            channel_id=111
        )
        
        await manager.add_message_to_batch(111, msg1)
        
        msg2 = ModerationMessage(
            message_id="123",
            user_id="456",
            content="Updated",
            timestamp=timestamp,
            guild_id=789,
            channel_id=111
        )
        
        await manager.update_message_in_batch(111, msg2)
        
        assert manager._channel_message_batches[111][0].content == "Updated"
        
        # Cleanup
        if manager._global_batch_timer:
            manager._global_batch_timer.cancel()

    @pytest.mark.asyncio
    async def test_update_message_in_batch_nonexistent_channel(self):
        """Test update_message_in_batch handles nonexistent channel."""
        manager = MessageBatchManager()
        
        timestamp = datetime.now(timezone.utc).isoformat()
        msg = ModerationMessage(
            message_id="123",
            user_id="456",
            content="Test",
            timestamp=timestamp,
            guild_id=789,
            channel_id=111
        )
        
        # Should not raise error
        await manager.update_message_in_batch(999, msg)

    def test_resolve_channel_name_no_bot(self):
        """Test _resolve_channel_name returns default when no bot."""
        manager = MessageBatchManager()
        result = manager._resolve_channel_name(123)
        assert result == "Channel 123"

    def test_resolve_channel_name_with_bot(self):
        """Test _resolve_channel_name gets name from bot."""
        manager = MessageBatchManager()
        
        mock_channel = Mock()
        mock_channel.name = "general"
        
        mock_bot = Mock()
        mock_bot.get_channel.return_value = mock_channel
        
        manager._bot_instance = mock_bot
        result = manager._resolve_channel_name(123)
        
        assert result == "general"
        mock_bot.get_channel.assert_called_once_with(123)

    def test_resolve_channel_name_channel_without_name(self):
        """Test _resolve_channel_name handles channel without name attribute."""
        manager = MessageBatchManager()
        
        mock_channel = Mock(spec=[])  # No 'name' attribute
        mock_bot = Mock()
        mock_bot.get_channel.return_value = mock_channel
        
        manager._bot_instance = mock_bot
        result = manager._resolve_channel_name(123)
        
        assert result == "Channel 123"

    @pytest.mark.asyncio
    async def test_group_messages_by_user_basic(self):
        """Test _group_messages_by_user groups messages correctly."""
        manager = MessageBatchManager()
        
        timestamp = datetime.now(timezone.utc).isoformat()
        msg1 = ModerationMessage(
            message_id="123",
            user_id="456",
            content="Message 1",
            timestamp=timestamp,
            guild_id=789,
            channel_id=111
        )
        
        msg2 = ModerationMessage(
            message_id="124",
            user_id="456",
            content="Message 2",
            timestamp=timestamp,
            guild_id=789,
            channel_id=111
        )
        
        with patch('modcord.moderation.message_batch_manager.get_past_actions', 
                   new_callable=AsyncMock, return_value=[]):
            with patch('modcord.moderation.message_batch_manager.app_config') as mock_config:
                mock_config.ai_settings = {"past_actions_lookback_minutes": 10080}
                users = await manager._group_messages_by_user([msg1, msg2])
        
        assert len(users) == 1
        assert users[0].user_id == "456"
        assert len(users[0].messages) == 2

    @pytest.mark.asyncio
    async def test_group_messages_by_user_multiple_users(self):
        """Test _group_messages_by_user handles multiple users."""
        manager = MessageBatchManager()
        
        timestamp = datetime.now(timezone.utc).isoformat()
        msg1 = ModerationMessage(
            message_id="123",
            user_id="456",
            content="User 1 message",
            timestamp=timestamp,
            guild_id=789,
            channel_id=111
        )
        
        msg2 = ModerationMessage(
            message_id="124",
            user_id="457",
            content="User 2 message",
            timestamp=timestamp,
            guild_id=789,
            channel_id=111
        )
        
        with patch('modcord.moderation.message_batch_manager.get_past_actions',
                   new_callable=AsyncMock, return_value=[]):
            with patch('modcord.moderation.message_batch_manager.app_config') as mock_config:
                mock_config.ai_settings = {"past_actions_lookback_minutes": 10080}
                users = await manager._group_messages_by_user([msg1, msg2])
        
        assert len(users) == 2
        assert users[0].user_id in ["456", "457"]
        assert users[1].user_id in ["456", "457"]

    @pytest.mark.asyncio
    async def test_group_messages_by_user_preserves_order(self):
        """Test _group_messages_by_user preserves first appearance order."""
        manager = MessageBatchManager()
        
        timestamp = datetime.now(timezone.utc).isoformat()
        msg1 = ModerationMessage(
            message_id="123",
            user_id="456",
            content="First user",
            timestamp=timestamp,
            guild_id=789,
            channel_id=111
        )
        
        msg2 = ModerationMessage(
            message_id="124",
            user_id="457",
            content="Second user",
            timestamp=timestamp,
            guild_id=789,
            channel_id=111
        )
        
        msg3 = ModerationMessage(
            message_id="125",
            user_id="456",
            content="First user again",
            timestamp=timestamp,
            guild_id=789,
            channel_id=111
        )
        
        with patch('modcord.moderation.message_batch_manager.get_past_actions',
                   new_callable=AsyncMock, return_value=[]):
            with patch('modcord.moderation.message_batch_manager.app_config') as mock_config:
                mock_config.ai_settings = {"past_actions_lookback_minutes": 10080}
                users = await manager._group_messages_by_user([msg1, msg2, msg3])
        
        # First user appeared first, so should be first in result
        assert users[0].user_id == "456"
        assert users[1].user_id == "457"
        assert len(users[0].messages) == 2

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Test shutdown cancels timer and clears batches."""
        manager = MessageBatchManager()
        
        # Add a message to create a timer
        timestamp = datetime.now(timezone.utc).isoformat()
        msg = ModerationMessage(
            message_id="123",
            user_id="456",
            content="Test",
            timestamp=timestamp,
            guild_id=789,
            channel_id=111
        )
        
        await manager.add_message_to_batch(111, msg)
        assert manager._global_batch_timer is not None
        assert len(manager._channel_message_batches) > 0
        
        await manager.shutdown()
        
        assert manager._global_batch_timer is None
        assert len(manager._channel_message_batches) == 0

    @pytest.mark.asyncio
    async def test_shutdown_no_timer(self):
        """Test shutdown works when no timer is active."""
        manager = MessageBatchManager()
        
        # Should not raise error
        await manager.shutdown()
        
        assert manager._global_batch_timer is None
