"""Tests for moderation_datatypes module."""

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
    WarnCommand,
    TimeoutCommand,
    KickCommand,
    BanCommand,
)


class TestActionType:
    """Tests for ActionType enum."""

    def test_action_type_values(self):
        """Test ActionType enum has correct values."""
        assert ActionType.BAN.value == "ban"
        assert ActionType.UNBAN.value == "unban"
        assert ActionType.KICK.value == "kick"
        assert ActionType.WARN.value == "warn"
        assert ActionType.DELETE.value == "delete"
        assert ActionType.TIMEOUT.value == "timeout"
        assert ActionType.NULL.value == "null"

    def test_action_type_str(self):
        """Test ActionType string representation."""
        assert str(ActionType.BAN) == "ban"
        assert str(ActionType.WARN) == "warn"
        assert str(ActionType.NULL) == "null"


class TestHumanizeTimestamp:
    """Tests for humanize_timestamp function."""

    def test_humanize_timestamp_with_z(self):
        """Test humanize_timestamp with Z suffix."""
        timestamp = "2023-10-28T12:30:45Z"
        result = humanize_timestamp(timestamp)
        assert "2023-10-28" in result
        assert "12:30:45" in result
        assert "UTC" in result

    def test_humanize_timestamp_with_offset(self):
        """Test humanize_timestamp with timezone offset."""
        timestamp = "2023-10-28T12:30:45+00:00"
        result = humanize_timestamp(timestamp)
        assert "2023-10-28" in result
        assert "UTC" in result

    def test_humanize_timestamp_format(self):
        """Test humanize_timestamp output format."""
        timestamp = "2023-10-28T12:30:45Z"
        result = humanize_timestamp(timestamp)
        assert result == "2023-10-28 12:30:45 UTC"


class TestActionData:
    """Tests for ActionData class."""

    def test_action_data_initialization(self):
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
        assert action.message_ids == ["msg1", "msg2"]

    def test_action_data_default_message_ids(self):
        """Test ActionData with default empty message_ids."""
        action = ActionData(
            user_id="123456",
            action=ActionType.WARN,
            reason="Test",
            timeout_duration=0,
            ban_duration=0
        )
        assert action.message_ids == []

    def test_add_message_ids(self):
        """Test adding message IDs to ActionData."""
        action = ActionData(
            user_id="123", action=ActionType.DELETE, reason="Test",
            timeout_duration=0, ban_duration=0
        )
        action.add_message_ids("msg1", "msg2")
        assert action.message_ids == ["msg1", "msg2"]

    def test_add_message_ids_duplicates(self):
        """Test that duplicate message IDs are not added."""
        action = ActionData(
            user_id="123", action=ActionType.DELETE, reason="Test",
            timeout_duration=0, ban_duration=0
        )
        action.add_message_ids("msg1", "msg1", "msg2")
        assert action.message_ids == ["msg1", "msg2"]

    def test_add_message_ids_empty_strings(self):
        """Test that empty strings are not added to message_ids."""
        action = ActionData(
            user_id="123", action=ActionType.DELETE, reason="Test",
            timeout_duration=0, ban_duration=0
        )
        action.add_message_ids("msg1", "", "  ", "msg2")
        assert action.message_ids == ["msg1", "msg2"]

    def test_replace_message_ids(self):
        """Test replacing message IDs."""
        action = ActionData(
            user_id="123", action=ActionType.DELETE, reason="Test",
            timeout_duration=0, ban_duration=0, message_ids=["old1", "old2"]
        )
        action.replace_message_ids(["new1", "new2", "new3"])
        assert action.message_ids == ["new1", "new2", "new3"]

    def test_to_wire_dict(self):
        """Test ActionData serialization to wire dict."""
        action = ActionData(
            user_id="123456",
            action=ActionType.BAN,
            reason="Test reason",
            timeout_duration=10,
            ban_duration=60,
            message_ids=["msg1", "msg2"]
        )
        wire_dict = action.to_wire_dict()
        assert wire_dict == {
            "user_id": "123456",
            "action": "ban",
            "reason": "Test reason",
            "message_ids": ["msg1", "msg2"],
            "timeout_duration": 10,
            "ban_duration": 60,
        }


class TestModerationImage:
    """Tests for ModerationImage class."""

    def test_moderation_image_initialization(self):
        """Test ModerationImage initialization."""
        img = ModerationImage(image_id="abc12345")
        assert img.image_id == "abc12345"
        assert img.pil_image is None

    def test_moderation_image_with_pil(self, mock_pil_image):
        """Test ModerationImage with PIL image."""
        img = ModerationImage(image_id="abc12345", pil_image=mock_pil_image)
        assert img.image_id == "abc12345"
        assert img.pil_image is not None


class TestModerationMessage:
    """Tests for ModerationMessage class."""

    def test_moderation_message_initialization(self):
        """Test ModerationMessage initialization."""
        timestamp = datetime.now(timezone.utc).isoformat()
        msg = ModerationMessage(
            message_id="123",
            user_id="456",
            content="Test content",
            timestamp=timestamp,
            guild_id=789,
            channel_id=111
        )
        assert msg.message_id == "123"
        assert msg.user_id == "456"
        assert msg.content == "Test content"
        assert msg.timestamp == timestamp
        assert msg.guild_id == 789
        assert msg.channel_id == 111
        assert msg.images == []
        assert msg.discord_message is None

    def test_moderation_message_with_images(self):
        """Test ModerationMessage with images."""
        timestamp = datetime.now(timezone.utc).isoformat()
        img = ModerationImage(image_id="img1")
        msg = ModerationMessage(
            message_id="123",
            user_id="456",
            content="Test",
            timestamp=timestamp,
            guild_id=789,
            channel_id=111,
            images=[img]
        )
        assert len(msg.images) == 1
        assert msg.images[0].image_id == "img1"


class TestModerationUser:
    """Tests for ModerationUser class."""

    def test_moderation_user_initialization(self):
        """Test ModerationUser initialization."""
        user = ModerationUser(
            user_id="123",
            username="TestUser"
        )
        assert user.user_id == "123"
        assert user.username == "TestUser"
        assert user.roles == []
        assert user.join_date is None
        assert user.messages == []
        assert user.past_actions == []

    def test_moderation_user_with_roles(self):
        """Test ModerationUser with roles."""
        user = ModerationUser(
            user_id="123",
            username="TestUser",
            roles=["Admin", "Moderator"]
        )
        assert user.roles == ["Admin", "Moderator"]

    def test_add_message(self):
        """Test adding a message to ModerationUser."""
        user = ModerationUser(user_id="123", username="TestUser")
        timestamp = datetime.now(timezone.utc).isoformat()
        msg = ModerationMessage(
            message_id="456",
            user_id="123",
            content="Test",
            timestamp=timestamp,
            guild_id=789,
            channel_id=111
        )
        user.add_message(msg)
        assert len(user.messages) == 1
        assert user.messages[0].message_id == "456"

    def test_to_model_payload(self):
        """Test ModerationUser serialization to model payload."""
        timestamp = "2023-10-28T12:00:00Z"
        user = ModerationUser(
            user_id="123",
            username="TestUser",
            roles=["Member"],
            join_date="2023-01-01T00:00:00Z"
        )
        msg = ModerationMessage(
            message_id="456",
            user_id="123",
            content="Hello",
            timestamp=timestamp,
            guild_id=789,
            channel_id=111
        )
        user.add_message(msg)
        
        payload = user.to_model_payload()
        assert payload["user_id"] == "123"
        assert payload["username"] == "TestUser"
        assert payload["roles"] == ["Member"]
        assert payload["join_date"] is not None
        assert payload["message_count"] == 1
        assert len(payload["messages"]) == 1
        assert payload["messages"][0]["message_id"] == "456"
        assert payload["messages"][0]["content"] == "Hello"

    def test_to_model_payload_no_join_date(self):
        """Test ModerationUser payload without join date."""
        user = ModerationUser(user_id="123", username="TestUser")
        payload = user.to_model_payload()
        assert payload["join_date"] is None


class TestModerationChannelBatch:
    """Tests for ModerationChannelBatch class."""

    def test_channel_batch_initialization(self):
        """Test ModerationChannelBatch initialization."""
        batch = ModerationChannelBatch(
            channel_id=123,
            channel_name="general"
        )
        assert batch.channel_id == 123
        assert batch.channel_name == "general"
        assert batch.users == []
        assert batch.history_users == []

    def test_add_user(self):
        """Test adding a user to batch."""
        batch = ModerationChannelBatch(channel_id=123, channel_name="general")
        user = ModerationUser(user_id="456", username="TestUser")
        batch.add_user(user)
        assert len(batch.users) == 1
        assert batch.users[0].user_id == "456"

    def test_extend_users(self):
        """Test extending batch with multiple users."""
        batch = ModerationChannelBatch(channel_id=123, channel_name="general")
        users = [
            ModerationUser(user_id="1", username="User1"),
            ModerationUser(user_id="2", username="User2")
        ]
        batch.extend_users(users)
        assert len(batch.users) == 2

    def test_set_history(self):
        """Test setting history users."""
        batch = ModerationChannelBatch(channel_id=123, channel_name="general")
        history = [ModerationUser(user_id="3", username="HistUser")]
        batch.set_history(history)
        assert len(batch.history_users) == 1
        assert batch.history_users[0].user_id == "3"

    def test_is_empty_no_users(self):
        """Test is_empty with no users."""
        batch = ModerationChannelBatch(channel_id=123, channel_name="general")
        assert batch.is_empty() is True

    def test_is_empty_users_no_messages(self):
        """Test is_empty with users but no messages."""
        batch = ModerationChannelBatch(channel_id=123, channel_name="general")
        user = ModerationUser(user_id="1", username="User1")
        batch.add_user(user)
        assert batch.is_empty() is True

    def test_is_empty_users_with_messages(self):
        """Test is_empty with users and messages."""
        batch = ModerationChannelBatch(channel_id=123, channel_name="general")
        user = ModerationUser(user_id="1", username="User1")
        timestamp = datetime.now(timezone.utc).isoformat()
        msg = ModerationMessage(
            message_id="2",
            user_id="1",
            content="Test",
            timestamp=timestamp,
            guild_id=789,
            channel_id=123
        )
        user.add_message(msg)
        batch.add_user(user)
        assert batch.is_empty() is False

    def test_to_model_payload(self):
        """Test batch conversion to model payload."""
        batch = ModerationChannelBatch(channel_id=123, channel_name="general")
        user = ModerationUser(user_id="1", username="User1")
        timestamp = datetime.now(timezone.utc).isoformat()
        msg = ModerationMessage(
            message_id="2",
            user_id="1",
            content="Test",
            timestamp=timestamp,
            guild_id=789,
            channel_id=123
        )
        user.add_message(msg)
        batch.add_user(user)
        
        payload = batch.to_model_payload()
        assert len(payload) == 1
        assert payload[0]["user_id"] == "1"

    def test_history_to_model_payload(self):
        """Test history conversion to model payload."""
        batch = ModerationChannelBatch(channel_id=123, channel_name="general")
        hist_user = ModerationUser(user_id="99", username="HistUser")
        batch.set_history([hist_user])
        
        payload = batch.history_to_model_payload()
        assert len(payload) == 1
        assert payload[0]["user_id"] == "99"


class TestCommandActions:
    """Tests for command action classes."""

    def test_warn_command_initialization(self):
        """Test WarnCommand initialization."""
        cmd = WarnCommand(reason="Breaking rules")
        assert cmd.action == ActionType.WARN
        assert cmd.reason == "Breaking rules"
        assert cmd.timeout_duration == 0
        assert cmd.ban_duration == 0

    def test_warn_command_default_reason(self):
        """Test WarnCommand with default reason."""
        cmd = WarnCommand()
        assert cmd.reason == "No reason provided."

    def test_timeout_command_initialization(self):
        """Test TimeoutCommand initialization."""
        cmd = TimeoutCommand(reason="Spam", duration_minutes=30)
        assert cmd.action == ActionType.TIMEOUT
        assert cmd.reason == "Spam"
        assert cmd.timeout_duration == 30
        assert cmd.ban_duration == 0

    def test_timeout_command_default_duration(self):
        """Test TimeoutCommand with default duration."""
        cmd = TimeoutCommand(reason="Test")
        assert cmd.timeout_duration == 10

    def test_kick_command_initialization(self):
        """Test KickCommand initialization."""
        cmd = KickCommand(reason="Toxicity")
        assert cmd.action == ActionType.KICK
        assert cmd.reason == "Toxicity"
        assert cmd.timeout_duration == 0
        assert cmd.ban_duration == 0

    def test_ban_command_initialization(self):
        """Test BanCommand initialization."""
        cmd = BanCommand(duration_minutes=1440, reason="Serious violation")
        assert cmd.action == ActionType.BAN
        assert cmd.reason == "Serious violation"
        assert cmd.ban_duration == 1440
        assert cmd.timeout_duration == 0

    def test_ban_command_permanent(self):
        """Test BanCommand with permanent ban."""
        cmd = BanCommand(duration_minutes=-1, reason="Permanent ban")
        assert cmd.ban_duration == -1
