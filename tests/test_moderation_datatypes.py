"""
Unit tests for moderation_datatypes module.

Tests the data structures used for moderation actions and message payloads.
"""

import pytest
from datetime import datetime, timezone

from modcord.moderation.moderation_datatypes import (
    ActionType,
    ActionData,
    ModerationImage,
    ModerationMessage,
    ModerationUser,
    ModerationChannelBatch,
    humanize_timestamp,
)


class TestHumanizeTimestamp:
    """Test the humanize_timestamp function."""

    def test_iso_format_with_z(self):
        """Test timestamp with Z suffix."""
        timestamp = "2024-01-15T10:30:00Z"
        result = humanize_timestamp(timestamp)
        assert result == "2024-01-15 10:30:00 UTC"

    def test_iso_format_with_offset(self):
        """Test timestamp with timezone offset."""
        timestamp = "2024-01-15T10:30:00+00:00"
        result = humanize_timestamp(timestamp)
        assert result == "2024-01-15 10:30:00 UTC"

    def test_future_timestamp_clamped(self):
        """Test that future timestamps are clamped to current time."""
        # Create a timestamp 1 year in the future
        future_time = datetime.now(timezone.utc).replace(year=datetime.now(timezone.utc).year + 1)
        future_timestamp = future_time.isoformat().replace('+00:00', 'Z')
        
        result = humanize_timestamp(future_timestamp)
        
        # Parse the result back to datetime
        result_dt = datetime.strptime(result, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        
        # Result should be at or before current time
        assert result_dt <= now
        # Should be recent (within last few seconds)
        assert (now - result_dt).total_seconds() < 5

    def test_current_timestamp_not_modified(self):
        """Test that current timestamps are not modified."""
        # Use a timestamp from a few seconds ago
        past_time = datetime.now(timezone.utc)
        past_timestamp = past_time.isoformat().replace('+00:00', 'Z')
        
        result = humanize_timestamp(past_timestamp)
        
        # Should match the input time (allowing for formatting differences)
        expected = past_time.strftime("%Y-%m-%d %H:%M:%S UTC")
        assert result == expected

    def test_old_timestamp_not_modified(self):
        """Test that old timestamps are preserved."""
        old_timestamp = "2023-06-15T10:30:00Z"
        result = humanize_timestamp(old_timestamp)
        assert result == "2023-06-15 10:30:00 UTC"


class TestActionData:
    """Test the ActionData class."""

    def test_initialization(self):
        """Test ActionData initialization."""
        action = ActionData(
            user_id="123456",
            action=ActionType.BAN,
            reason="Test reason",
            timeout_duration=0,
            ban_duration=60,
            message_ids=["msg1", "msg2"]
        )
        
        assert action.user_id == "123456"
        assert action.action == ActionType.BAN
        assert action.reason == "Test reason"
        assert action.timeout_duration == 0
        assert action.ban_duration == 60
        assert len(action.message_ids) == 2

    def test_add_message_ids(self):
        """Test adding message IDs."""
        action = ActionData(
            user_id="123",
            action=ActionType.WARN,
            reason="Test",
            timeout_duration=0,
            ban_duration=0
        )
        
        action.add_message_ids("msg1", "msg2", "msg3")
        assert len(action.message_ids) == 3
        assert "msg1" in action.message_ids

    def test_add_message_ids_no_duplicates(self):
        """Test that duplicate message IDs are not added."""
        action = ActionData(
            user_id="123",
            action=ActionType.WARN,
            reason="Test",
            timeout_duration=0,
            ban_duration=0
        )
        
        action.add_message_ids("msg1", "msg1", "msg2")
        assert len(action.message_ids) == 2

    def test_add_message_ids_strips_whitespace(self):
        """Test that message IDs are stripped of whitespace."""
        action = ActionData(
            user_id="123",
            action=ActionType.WARN,
            reason="Test",
            timeout_duration=0,
            ban_duration=0
        )
        
        action.add_message_ids("  msg1  ", "msg2")
        assert "msg1" in action.message_ids
        assert "  msg1  " not in action.message_ids

    def test_replace_message_ids(self):
        """Test replacing message IDs."""
        action = ActionData(
            user_id="123",
            action=ActionType.WARN,
            reason="Test",
            timeout_duration=0,
            ban_duration=0,
            message_ids=["old1", "old2"]
        )
        
        action.replace_message_ids(["new1", "new2", "new3"])
        assert len(action.message_ids) == 3
        assert "old1" not in action.message_ids
        assert "new1" in action.message_ids

    def test_to_wire_dict(self):
        """Test conversion to wire dictionary."""
        action = ActionData(
            user_id="123456",
            action=ActionType.BAN,
            reason="Test reason",
            timeout_duration=0,
            ban_duration=60,
            message_ids=["msg1"]
        )
        
        wire_dict = action.to_wire_dict()
        
        assert wire_dict["user_id"] == "123456"
        assert wire_dict["action"] == "ban"
        assert wire_dict["reason"] == "Test reason"
        assert wire_dict["ban_duration"] == 60
        assert isinstance(wire_dict["message_ids"], list)


class TestModerationImage:
    """Test the ModerationImage class."""

    def test_initialization(self):
        """Test ModerationImage initialization."""
        img = ModerationImage(image_id="abc123", pil_image=None)
        
        assert img.image_id == "abc123"
        assert img.pil_image is None


class TestModerationMessage:
    """Test the ModerationMessage class."""

    def test_initialization(self):
        """Test ModerationMessage initialization."""
        msg = ModerationMessage(
            message_id="123",
            user_id="456",
            content="Test message",
            timestamp="2024-01-15T10:30:00Z",
            guild_id=789,
            channel_id=101112
        )
        
        assert msg.message_id == "123"
        assert msg.user_id == "456"
        assert msg.content == "Test message"
        assert msg.guild_id == 789
        assert msg.channel_id == 101112
        assert len(msg.images) == 0

    def test_with_images(self):
        """Test ModerationMessage with images."""
        img1 = ModerationImage(image_id="img1")
        img2 = ModerationImage(image_id="img2")
        
        msg = ModerationMessage(
            message_id="123",
            user_id="456",
            content="Test",
            timestamp="2024-01-15T10:30:00Z",
            guild_id=789,
            channel_id=101112,
            images=[img1, img2]
        )
        
        assert len(msg.images) == 2


class TestModerationUser:
    """Test the ModerationUser class."""

    def test_initialization(self):
        """Test ModerationUser initialization."""
        user = ModerationUser(
            user_id="123",
            username="TestUser",
            roles=["Member", "Verified"],
            join_date="2024-01-01T00:00:00Z"
        )
        
        assert user.user_id == "123"
        assert user.username == "TestUser"
        assert len(user.roles) == 2
        assert len(user.messages) == 0

    def test_add_message(self):
        """Test adding messages to user."""
        user = ModerationUser(
            user_id="123",
            username="TestUser"
        )
        
        msg = ModerationMessage(
            message_id="1",
            user_id="123",
            content="Test",
            timestamp="2024-01-15T10:30:00Z",
            guild_id=1,
            channel_id=1
        )
        
        user.add_message(msg)
        assert len(user.messages) == 1

    def test_to_model_payload(self):
        """Test conversion to model payload."""
        msg = ModerationMessage(
            message_id="1",
            user_id="123",
            content="Test message",
            timestamp="2024-01-15T10:30:00Z",
            guild_id=1,
            channel_id=1
        )
        
        user = ModerationUser(
            user_id="123",
            username="TestUser",
            roles=["Member"],
            join_date="2024-01-01T00:00:00Z",
            messages=[msg]
        )
        
        # Format messages as they would be in batch processing
        messages_payload = [msg.to_model_payload(is_history=False, image_id_map={})]
        payload = user.to_model_payload(messages_payload=messages_payload)
        
        assert payload["user_id"] == "123"
        assert payload["username"] == "TestUser"
        assert payload["message_count"] == 1
        assert len(payload["messages"]) == 1
        assert payload["messages"][0]["message_id"] == "1"

    def test_to_model_payload_with_past_actions(self):
        """Test conversion to model payload with past actions."""
        msg = ModerationMessage(
            message_id="1",
            user_id="123",
            content="Test message",
            timestamp="2024-01-15T10:30:00Z",
            guild_id=1,
            channel_id=1
        )
        
        past_actions = [
            {
                "action_type": "warn",
                "reason": "Spamming",
                "timestamp": "2024-01-10T10:00:00Z",
                "metadata": {}
            },
            {
                "action_type": "timeout",
                "reason": "Repeated spamming",
                "timestamp": "2024-01-12T15:30:00Z",
                "metadata": {"timeout_duration": 60}
            },
            {
                "action_type": "ban",
                "reason": "Severe violations",
                "timestamp": "2024-01-14T09:00:00Z",
                "metadata": {"ban_duration": -1}
            }
        ]
        
        user = ModerationUser(
            user_id="123",
            username="TestUser",
            roles=["Member"],
            join_date="2024-01-01T00:00:00Z",
            messages=[msg],
            past_actions=past_actions
        )
        
        messages_payload = [msg.to_model_payload(is_history=False, image_id_map={})]
        payload = user.to_model_payload(messages_payload=messages_payload)
        
        assert payload["user_id"] == "123"
        assert len(payload["past_actions"]) == 3
        
        # Check warn action formatting
        assert payload["past_actions"][0]["action"] == "warn"
        assert payload["past_actions"][0]["reason"] == "Spamming"
        assert "duration" not in payload["past_actions"][0]
        
        # Check timeout action with duration
        assert payload["past_actions"][1]["action"] == "timeout"
        assert payload["past_actions"][1]["duration"] == "60 minutes"
        
        # Check permanent ban
        assert payload["past_actions"][2]["action"] == "ban"
        assert payload["past_actions"][2]["duration"] == "permanent"

    def test_to_model_payload_with_empty_past_actions(self):
        """Test that empty past_actions list is handled correctly."""
        msg = ModerationMessage(
            message_id="1",
            user_id="123",
            content="Test message",
            timestamp="2024-01-15T10:30:00Z",
            guild_id=1,
            channel_id=1
        )
        
        user = ModerationUser(
            user_id="123",
            username="TestUser",
            messages=[msg],
            past_actions=[]
        )
        
        messages_payload = [msg.to_model_payload(is_history=False, image_id_map={})]
        payload = user.to_model_payload(messages_payload=messages_payload)
        
        assert payload["past_actions"] == []

    def test_to_model_payload_past_actions_without_metadata(self):
        """Test past actions that don't have metadata."""
        past_actions = [
            {
                "action_type": "kick",
                "reason": "Inappropriate behavior",
                "timestamp": "2024-01-10T10:00:00Z",
                "metadata": None
            }
        ]
        
        user = ModerationUser(
            user_id="123",
            username="TestUser",
            past_actions=past_actions
        )
        
        # Create a dummy message for messages_payload
        messages_payload = []
        payload = user.to_model_payload(messages_payload=messages_payload)
        
        assert len(payload["past_actions"]) == 1
        assert payload["past_actions"][0]["action"] == "kick"
        assert "duration" not in payload["past_actions"][0]


class TestModerationChannelBatch:
    """Test the ModerationChannelBatch class."""

    def test_initialization(self):
        """Test ModerationChannelBatch initialization."""
        batch = ModerationChannelBatch(
            channel_id=123,
            channel_name="general"
        )
        
        assert batch.channel_id == 123
        assert batch.channel_name == "general"
        assert len(batch.users) == 0
        assert len(batch.history_users) == 0

    def test_add_user(self):
        """Test adding user to batch."""
        batch = ModerationChannelBatch(
            channel_id=123,
            channel_name="general"
        )
        
        user = ModerationUser(user_id="1", username="User1")
        batch.add_user(user)
        
        assert len(batch.users) == 1

    def test_extend_users(self):
        """Test extending users list."""
        batch = ModerationChannelBatch(
            channel_id=123,
            channel_name="general"
        )
        
        users = [
            ModerationUser(user_id="1", username="User1"),
            ModerationUser(user_id="2", username="User2"),
        ]
        
        batch.extend_users(users)
        assert len(batch.users) == 2

    def test_set_history(self):
        """Test setting history users."""
        batch = ModerationChannelBatch(
            channel_id=123,
            channel_name="general"
        )
        
        history = [
            ModerationUser(user_id="3", username="User3"),
        ]
        
        batch.set_history(history)
        assert len(batch.history_users) == 1

    def test_is_empty_no_users(self):
        """Test is_empty with no users."""
        batch = ModerationChannelBatch(
            channel_id=123,
            channel_name="general"
        )
        
        assert batch.is_empty() is True

    def test_is_empty_with_users_no_messages(self):
        """Test is_empty with users but no messages."""
        batch = ModerationChannelBatch(
            channel_id=123,
            channel_name="general"
        )
        
        user = ModerationUser(user_id="1", username="User1")
        batch.add_user(user)
        
        assert batch.is_empty() is True

    def test_is_empty_with_messages(self):
        """Test is_empty with users and messages."""
        msg = ModerationMessage(
            message_id="1",
            user_id="1",
            content="Test",
            timestamp="2024-01-15T10:30:00Z",
            guild_id=1,
            channel_id=1
        )
        
        user = ModerationUser(user_id="1", username="User1", messages=[msg])
        
        batch = ModerationChannelBatch(
            channel_id=123,
            channel_name="general"
        )
        batch.add_user(user)
        
        assert batch.is_empty() is False

    def test_to_multimodal_payload_basic(self):
        """Test basic multimodal payload generation."""
        msg = ModerationMessage(
            message_id="1",
            user_id="1",
            content="Test",
            timestamp="2024-01-15T10:30:00Z",
            guild_id=1,
            channel_id=1
        )
        
        user = ModerationUser(user_id="1", username="User1", messages=[msg])
        
        batch = ModerationChannelBatch(
            channel_id=123,
            channel_name="general",
            users=[user]
        )
        
        payload, images, image_map = batch.to_multimodal_payload()
        
        assert len(payload["users"]) == 1
        assert payload["users"][0]["user_id"] == "1"
        assert len(images) == 0
        assert len(image_map) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
