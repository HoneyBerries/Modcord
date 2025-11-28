"""Tests for discord_utils module."""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock, patch
import discord
from datetime import datetime, timezone

from modcord.util.discord_utils import (
    format_duration,
    parse_duration_to_minutes,
    is_ignored_author,
    has_elevated_permissions,
    bot_can_manage_messages,
    iter_moderatable_channels,
    delete_message,
    DURATIONS,
    PERMANENT_DURATION,
)
from modcord.datatypes.action_datatypes import ActionType


class TestFormatDuration:
    """Test the format_duration function."""

    def test_permanent_duration(self):
        """Test formatting of permanent (0 seconds) duration."""
        assert format_duration(0) == PERMANENT_DURATION

    def test_seconds_only(self):
        """Test formatting durations less than a minute."""
        assert format_duration(30) == "30 secs"
        assert format_duration(59) == "59 secs"

    def test_minutes_only(self):
        """Test formatting durations in minutes."""
        assert format_duration(60) == "1 mins"
        assert format_duration(120) == "2 mins"
        assert format_duration(3540) == "59 mins"

    def test_hours(self):
        """Test formatting durations in hours."""
        assert format_duration(3600) == "1 hour"
        assert format_duration(7200) == "2 hours"
        assert format_duration(86399) == "23 hours"

    def test_days(self):
        """Test formatting durations in days."""
        assert format_duration(86400) == "1 day"
        assert format_duration(172800) == "2 days"
        assert format_duration(604800) == "7 days"


class TestParseDurationToMinutes:
    """Test the parse_duration_to_minutes function."""

    def test_valid_durations(self):
        """Test parsing of valid duration strings."""
        assert parse_duration_to_minutes("60 secs") == 1
        assert parse_duration_to_minutes("5 mins") == 5
        assert parse_duration_to_minutes("1 hour") == 60
        assert parse_duration_to_minutes("1 day") == 24 * 60
        assert parse_duration_to_minutes("1 week") == 7 * 24 * 60

    def test_permanent_duration(self):
        """Test parsing of permanent duration."""
        assert parse_duration_to_minutes(PERMANENT_DURATION) == 0

    def test_invalid_duration(self):
        """Test parsing of invalid duration strings."""
        assert parse_duration_to_minutes("invalid") == 0
        assert parse_duration_to_minutes("") == 0


class TestBotCanManageMessages:
    """Test the bot_can_manage_messages function."""

    def test_guild_without_me_attribute(self):
        """Test when guild doesn't have 'me' attribute."""
        guild = MagicMock()
        guild.me = None
        channel = MagicMock()
        
        assert bot_can_manage_messages(channel, guild) is True

    def test_bot_has_permissions(self):
        """Test when bot has required permissions."""
        guild = MagicMock()
        channel = MagicMock()
        
        permissions = MagicMock()
        permissions.read_messages = True
        permissions.manage_messages = True
        channel.permissions_for.return_value = permissions
        
        assert bot_can_manage_messages(channel, guild) is True

    def test_bot_missing_read_permission(self):
        """Test when bot lacks read permission."""
        guild = MagicMock()
        channel = MagicMock()
        
        permissions = MagicMock()
        permissions.read_messages = False
        permissions.manage_messages = True
        channel.permissions_for.return_value = permissions
        
        assert bot_can_manage_messages(channel, guild) is False

    def test_bot_missing_manage_permission(self):
        """Test when bot lacks manage permission."""
        guild = MagicMock()
        channel = MagicMock()
        
        permissions = MagicMock()
        permissions.read_messages = True
        permissions.manage_messages = False
        channel.permissions_for.return_value = permissions
        
        assert bot_can_manage_messages(channel, guild) is False

    def test_permission_check_exception(self):
        """Test when permission check raises exception."""
        guild = MagicMock()
        channel = MagicMock()
        channel.permissions_for.side_effect = Exception("Test error")
        
        assert bot_can_manage_messages(channel, guild) is False


class TestIterModeratableChannels:
    """Test the iter_moderatable_channels function."""

    def test_empty_guild(self):
        """Test iteration over guild with no channels."""
        guild = MagicMock()
        guild.text_channels = []
        
        channels = list(iter_moderatable_channels(guild))
        assert len(channels) == 0

    def test_guild_with_manageable_channels(self):
        """Test iteration over guild with manageable channels."""
        guild = MagicMock()
        
        channel1 = MagicMock()
        channel1.name = "general"
        channel2 = MagicMock()
        channel2.name = "moderation"
        
        guild.text_channels = [channel1, channel2]
        
        # Mock permissions
        permissions = MagicMock()
        permissions.read_messages = True
        permissions.manage_messages = True
        channel1.permissions_for.return_value = permissions
        channel2.permissions_for.return_value = permissions
        
        channels = list(iter_moderatable_channels(guild))
        assert len(channels) == 2

    def test_guild_with_mixed_permissions(self):
        """Test iteration filters out channels without permissions."""
        guild = MagicMock()
        
        channel1 = MagicMock()
        channel1.name = "general"
        channel2 = MagicMock()
        channel2.name = "restricted"
        
        guild.text_channels = [channel1, channel2]
        
        # channel1 has permissions
        permissions1 = MagicMock()
        permissions1.read_messages = True
        permissions1.manage_messages = True
        channel1.permissions_for.return_value = permissions1
        
        # channel2 lacks permissions
        permissions2 = MagicMock()
        permissions2.read_messages = False
        permissions2.manage_messages = False
        channel2.permissions_for.return_value = permissions2
        
        channels = list(iter_moderatable_channels(guild))
        assert len(channels) == 1
        assert channels[0] == channel1


class TestSafeDeleteMessage:
    """Test the delete_message function."""

    @pytest.mark.asyncio
    async def test_successful_deletion(self):
        """Test successful message deletion."""
        message = AsyncMock()
        message.delete = AsyncMock()
        
        result = await delete_message(message)
        
        assert result is True
        message.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_message_not_found(self):
        """Test deletion when message not found."""
        import discord
        
        message = AsyncMock()
        message.delete = AsyncMock(side_effect=discord.NotFound(MagicMock(), "Not found"))
        
        result = await delete_message(message)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_forbidden_deletion(self):
        """Test deletion when forbidden."""
        import discord
        
        message = AsyncMock()
        message.id = 12345
        message.delete = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Forbidden"))
        
        result = await delete_message(message)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_general_exception(self):
        """Test deletion with general exception."""
        message = AsyncMock()
        message.id = 12345
        message.delete = AsyncMock(side_effect=Exception("Test error"))
        
        result = await delete_message(message)
        
        assert result is False


class TestActionType:
    """Test ActionType enum."""

    def test_action_type_values(self):
        """Test that ActionType enum has expected values."""
        assert ActionType.BAN.value == "ban"
        assert ActionType.KICK.value == "kick"
        assert ActionType.WARN.value == "warn"
        assert ActionType.TIMEOUT.value == "timeout"
        assert ActionType.DELETE.value == "delete"
        assert ActionType.UNBAN.value == "unban"
        assert ActionType.NULL.value == "null"

    def test_action_type_string_conversion(self):
        """Test ActionType string representation."""
        assert str(ActionType.BAN) == "ban"
        assert str(ActionType.WARN) == "warn"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
