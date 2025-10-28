"""Tests for discord_utils module."""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock, patch
import discord
from datetime import datetime, timezone

from modcord.util.discord_utils import (
    format_duration,
    parse_duration_to_minutes,
    build_dm_message,
    is_ignored_author,
    has_elevated_permissions,
    bot_can_manage_messages,
    DURATIONS,
    PERMANENT_DURATION,
)
from modcord.moderation.moderation_datatypes import ActionType


class TestFormatDuration:
    """Tests for format_duration function."""

    def test_zero_seconds(self):
        """Test formatting zero seconds."""
        result = format_duration(0)
        assert result == PERMANENT_DURATION

    def test_seconds_under_minute(self):
        """Test formatting seconds under 60."""
        assert format_duration(30) == "30 secs"
        assert format_duration(59) == "59 secs"

    def test_minutes(self):
        """Test formatting minutes."""
        assert format_duration(60) == "1 mins"
        assert format_duration(120) == "2 mins"
        assert format_duration(1800) == "30 mins"

    def test_hours(self):
        """Test formatting hours."""
        assert format_duration(3600) == "1 hour"
        assert format_duration(7200) == "2 hours"
        assert format_duration(10800) == "3 hours"

    def test_days(self):
        """Test formatting days."""
        assert format_duration(86400) == "1 day"
        assert format_duration(172800) == "2 days"
        assert format_duration(604800) == "7 days"


class TestParseDurationToMinutes:
    """Tests for parse_duration_to_minutes function."""

    def test_known_durations(self):
        """Test parsing known duration strings."""
        assert parse_duration_to_minutes("60 secs") == 1
        assert parse_duration_to_minutes("5 mins") == 5
        assert parse_duration_to_minutes("10 mins") == 10
        assert parse_duration_to_minutes("1 hour") == 60
        assert parse_duration_to_minutes("1 day") == 24 * 60

    def test_permanent_duration(self):
        """Test parsing permanent duration."""
        result = parse_duration_to_minutes(PERMANENT_DURATION)
        assert result == 0

    def test_unknown_duration(self):
        """Test parsing unknown duration returns 0."""
        result = parse_duration_to_minutes("unknown duration")
        assert result == 0


class TestBuildDmMessage:
    """Tests for build_dm_message function."""

    def test_ban_message_temporary(self):
        """Test building DM message for temporary ban."""
        msg = build_dm_message(ActionType.BAN, "Test Guild", "Spam", "1 day")
        assert "banned" in msg
        assert "Test Guild" in msg
        assert "for 1 day" in msg
        assert "Spam" in msg

    def test_ban_message_permanent(self):
        """Test building DM message for permanent ban."""
        msg = build_dm_message(ActionType.BAN, "Test Guild", "Serious violation", PERMANENT_DURATION)
        assert "banned" in msg
        assert "permanently" in msg
        assert "Test Guild" in msg

    def test_kick_message(self):
        """Test building DM message for kick."""
        msg = build_dm_message(ActionType.KICK, "Test Guild", "Rule violation")
        assert "kicked" in msg
        assert "Test Guild" in msg
        assert "Rule violation" in msg

    def test_timeout_message(self):
        """Test building DM message for timeout."""
        msg = build_dm_message(ActionType.TIMEOUT, "Test Guild", "Harassment", "30 mins")
        assert "timed out" in msg
        assert "Test Guild" in msg
        assert "30 mins" in msg
        assert "Harassment" in msg

    def test_warn_message(self):
        """Test building DM message for warning."""
        msg = build_dm_message(ActionType.WARN, "Test Guild", "Minor infraction")
        assert "warning" in msg
        assert "Test Guild" in msg
        assert "Minor infraction" in msg

    def test_null_action(self):
        """Test building DM message for null action."""
        msg = build_dm_message(ActionType.NULL, "Test Guild", "Test")
        assert msg == ""

    def test_delete_action(self):
        """Test building DM message for delete action."""
        msg = build_dm_message(ActionType.DELETE, "Test Guild", "Test")
        assert msg == ""


class TestIsIgnoredAuthor:
    """Tests for is_ignored_author function."""

    def test_bot_user(self):
        """Test that bot users are ignored."""
        user = MagicMock()
        user.bot = True
        assert is_ignored_author(user) is True

    def test_non_member_user(self):
        """Test that non-Member users are ignored."""
        user = MagicMock(spec=discord.User)
        user.bot = False
        assert is_ignored_author(user) is True

    def test_member_user(self):
        """Test that regular Member users are not ignored."""
        member = MagicMock(spec=discord.Member)
        member.bot = False
        assert is_ignored_author(member) is False

    def test_bot_member(self):
        """Test that bot Members are ignored."""
        member = MagicMock(spec=discord.Member)
        member.bot = True
        assert is_ignored_author(member) is True


class TestHasElevatedPermissions:
    """Tests for has_elevated_permissions function."""

    def test_administrator_permission(self):
        """Test that administrator permission is elevated."""
        member = MagicMock(spec=discord.Member)
        member.guild_permissions.administrator = True
        member.guild_permissions.manage_guild = False
        member.guild_permissions.moderate_members = False
        assert has_elevated_permissions(member) is True

    def test_manage_guild_permission(self):
        """Test that manage_guild permission is elevated."""
        member = MagicMock(spec=discord.Member)
        member.guild_permissions.administrator = False
        member.guild_permissions.manage_guild = True
        member.guild_permissions.moderate_members = False
        assert has_elevated_permissions(member) is True

    def test_moderate_members_permission(self):
        """Test that moderate_members permission is elevated."""
        member = MagicMock(spec=discord.Member)
        member.guild_permissions.administrator = False
        member.guild_permissions.manage_guild = False
        member.guild_permissions.moderate_members = True
        assert has_elevated_permissions(member) is True

    def test_no_elevated_permissions(self):
        """Test that regular member has no elevated permissions."""
        member = MagicMock(spec=discord.Member)
        member.guild_permissions.administrator = False
        member.guild_permissions.manage_guild = False
        member.guild_permissions.moderate_members = False
        assert has_elevated_permissions(member) is False

    def test_non_member(self):
        """Test that non-Member returns False."""
        user = MagicMock(spec=discord.User)
        assert has_elevated_permissions(user) is False


class TestBotCanManageMessages:
    """Tests for bot_can_manage_messages function."""

    def test_bot_has_permissions(self):
        """Test when bot has read and manage message permissions."""
        channel = MagicMock(spec=discord.TextChannel)
        guild = MagicMock()
        bot_member = MagicMock()
        guild.me = bot_member
        
        permissions = MagicMock()
        permissions.read_messages = True
        permissions.manage_messages = True
        channel.permissions_for.return_value = permissions
        
        assert bot_can_manage_messages(channel, guild) is True

    def test_bot_missing_read_permission(self):
        """Test when bot lacks read permission."""
        channel = MagicMock(spec=discord.TextChannel)
        guild = MagicMock()
        bot_member = MagicMock()
        guild.me = bot_member
        
        permissions = MagicMock()
        permissions.read_messages = False
        permissions.manage_messages = True
        channel.permissions_for.return_value = permissions
        
        assert bot_can_manage_messages(channel, guild) is False

    def test_bot_missing_manage_permission(self):
        """Test when bot lacks manage messages permission."""
        channel = MagicMock(spec=discord.TextChannel)
        guild = MagicMock()
        bot_member = MagicMock()
        guild.me = bot_member
        
        permissions = MagicMock()
        permissions.read_messages = True
        permissions.manage_messages = False
        channel.permissions_for.return_value = permissions
        
        assert bot_can_manage_messages(channel, guild) is False

    def test_guild_no_me_attribute(self):
        """Test when guild has no 'me' attribute."""
        channel = MagicMock(spec=discord.TextChannel)
        guild = MagicMock()
        guild.me = None
        
        # Should return True when me is None (fallback)
        assert bot_can_manage_messages(channel, guild) is True

    def test_permission_check_exception(self):
        """Test handling of exceptions during permission check."""
        channel = MagicMock(spec=discord.TextChannel)
        guild = MagicMock()
        bot_member = MagicMock()
        guild.me = bot_member
        
        channel.permissions_for.side_effect = Exception("Permission error")
        
        assert bot_can_manage_messages(channel, guild) is False


class TestDurationConstants:
    """Tests for duration constants."""

    def test_durations_dict_structure(self):
        """Test that DURATIONS dict has expected structure."""
        assert isinstance(DURATIONS, dict)
        assert "60 secs" in DURATIONS
        assert "1 hour" in DURATIONS
        assert "1 day" in DURATIONS
        assert PERMANENT_DURATION in DURATIONS

    def test_durations_values(self):
        """Test that DURATIONS has correct values."""
        assert DURATIONS["60 secs"] == 1
        assert DURATIONS["5 mins"] == 5
        assert DURATIONS["1 hour"] == 60
        assert DURATIONS["1 day"] == 24 * 60
        assert DURATIONS[PERMANENT_DURATION] == 0

    def test_permanent_duration_constant(self):
        """Test PERMANENT_DURATION constant value."""
        assert PERMANENT_DURATION == "Till the end of time"
