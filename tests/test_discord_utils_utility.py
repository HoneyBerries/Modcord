"""Extended tests for discord_utils module - utility functions."""

import pytest
from unittest.mock import Mock, MagicMock
from modcord.util.discord_utils import (
    PERMANENT_DURATION,
    DURATIONS,
    DURATION_CHOICES,
    bot_can_manage_messages,
    iter_moderatable_channels,
    is_ignored_author,
    has_elevated_permissions,
    format_duration,
)


class TestConstants:
    """Tests for module constants."""

    def test_permanent_duration_constant(self):
        """Test PERMANENT_DURATION constant value."""
        assert PERMANENT_DURATION == "Till the end of time"

    def test_durations_dict(self):
        """Test DURATIONS dictionary has expected keys."""
        assert "60 secs" in DURATIONS
        assert "5 mins" in DURATIONS
        assert "1 hour" in DURATIONS
        assert "1 day" in DURATIONS
        assert "1 week" in DURATIONS
        assert PERMANENT_DURATION in DURATIONS

    def test_durations_values(self):
        """Test DURATIONS dictionary values."""
        assert DURATIONS["60 secs"] == 1
        assert DURATIONS["5 mins"] == 5
        assert DURATIONS["10 mins"] == 10
        assert DURATIONS["1 hour"] == 60
        assert DURATIONS[PERMANENT_DURATION] == 0

    def test_duration_choices_list(self):
        """Test DURATION_CHOICES is a list of duration keys."""
        assert isinstance(DURATION_CHOICES, list)
        assert len(DURATION_CHOICES) > 0
        assert all(key in DURATIONS for key in DURATION_CHOICES)


class TestBotCanManageMessages:
    """Tests for bot_can_manage_messages function."""

    def test_bot_can_manage_messages_with_permissions(self):
        """Test bot_can_manage_messages returns True when bot has permissions."""
        mock_channel = Mock()
        mock_guild = Mock()
        mock_me = Mock()
        mock_guild.me = mock_me
        
        mock_permissions = Mock()
        mock_permissions.read_messages = True
        mock_permissions.manage_messages = True
        mock_channel.permissions_for.return_value = mock_permissions
        
        result = bot_can_manage_messages(mock_channel, mock_guild)
        assert result is True

    def test_bot_can_manage_messages_without_read_permission(self):
        """Test bot_can_manage_messages returns False without read permission."""
        mock_channel = Mock()
        mock_guild = Mock()
        mock_me = Mock()
        mock_guild.me = mock_me
        
        mock_permissions = Mock()
        mock_permissions.read_messages = False
        mock_permissions.manage_messages = True
        mock_channel.permissions_for.return_value = mock_permissions
        
        result = bot_can_manage_messages(mock_channel, mock_guild)
        assert result is False

    def test_bot_can_manage_messages_without_manage_permission(self):
        """Test bot_can_manage_messages returns False without manage permission."""
        mock_channel = Mock()
        mock_guild = Mock()
        mock_me = Mock()
        mock_guild.me = mock_me
        
        mock_permissions = Mock()
        mock_permissions.read_messages = True
        mock_permissions.manage_messages = False
        mock_channel.permissions_for.return_value = mock_permissions
        
        result = bot_can_manage_messages(mock_channel, mock_guild)
        assert result is False

    def test_bot_can_manage_messages_no_guild_me(self):
        """Test bot_can_manage_messages returns True when guild.me is None."""
        mock_channel = Mock()
        mock_guild = Mock()
        mock_guild.me = None
        
        result = bot_can_manage_messages(mock_channel, mock_guild)
        assert result is True

    def test_bot_can_manage_messages_exception(self):
        """Test bot_can_manage_messages returns False on exception."""
        mock_channel = Mock()
        mock_guild = Mock()
        mock_guild.me = Mock()
        mock_channel.permissions_for.side_effect = Exception("Permission error")
        
        result = bot_can_manage_messages(mock_channel, mock_guild)
        assert result is False


class TestIterModerateableChannels:
    """Tests for iter_moderatable_channels function."""

    def test_iter_moderatable_channels_yields_manageable(self):
        """Test iter_moderatable_channels yields channels with manage permissions."""
        mock_guild = Mock()
        mock_channel1 = Mock()
        mock_channel2 = Mock()
        mock_guild.text_channels = [mock_channel1, mock_channel2]
        mock_guild.me = Mock()
        
        mock_perms = Mock()
        mock_perms.read_messages = True
        mock_perms.manage_messages = True
        mock_channel1.permissions_for.return_value = mock_perms
        mock_channel2.permissions_for.return_value = mock_perms
        
        channels = list(iter_moderatable_channels(mock_guild))
        assert len(channels) == 2

    def test_iter_moderatable_channels_skips_unmanageable(self):
        """Test iter_moderatable_channels skips channels without permissions."""
        mock_guild = Mock()
        mock_channel1 = Mock()
        mock_channel2 = Mock()
        mock_guild.text_channels = [mock_channel1, mock_channel2]
        mock_guild.me = Mock()
        
        mock_perms1 = Mock()
        mock_perms1.read_messages = True
        mock_perms1.manage_messages = True
        
        mock_perms2 = Mock()
        mock_perms2.read_messages = False
        mock_perms2.manage_messages = False
        
        mock_channel1.permissions_for.return_value = mock_perms1
        mock_channel2.permissions_for.return_value = mock_perms2
        
        channels = list(iter_moderatable_channels(mock_guild))
        assert len(channels) == 1
        assert channels[0] is mock_channel1

    def test_iter_moderatable_channels_no_text_channels(self):
        """Test iter_moderatable_channels with no text channels."""
        mock_guild = Mock()
        mock_guild.text_channels = []
        
        channels = list(iter_moderatable_channels(mock_guild))
        assert len(channels) == 0


class TestIsIgnoredAuthor:
    """Tests for is_ignored_author function."""

    def test_is_ignored_author_bot(self):
        """Test is_ignored_author returns True for bots."""
        mock_author = Mock()
        mock_author.bot = True
        
        result = is_ignored_author(mock_author)
        assert result is True

    def test_is_ignored_author_not_member(self):
        """Test is_ignored_author returns True for non-members."""
        from discord import User
        mock_author = Mock(spec=User)
        mock_author.bot = False
        
        result = is_ignored_author(mock_author)
        assert result is True

    def test_is_ignored_author_valid_member(self):
        """Test is_ignored_author returns False for valid member."""
        from discord import Member
        mock_author = Mock(spec=Member)
        mock_author.bot = False
        
        result = is_ignored_author(mock_author)
        assert result is False


class TestHasElevatedPermissions:
    """Tests for has_elevated_permissions function."""

    def test_has_elevated_permissions_administrator(self):
        """Test has_elevated_permissions returns True for administrator."""
        from discord import Member
        mock_member = Mock(spec=Member)
        mock_perms = Mock()
        mock_perms.administrator = True
        mock_perms.manage_guild = False
        mock_perms.moderate_members = False
        mock_member.guild_permissions = mock_perms
        
        result = has_elevated_permissions(mock_member)
        assert result is True

    def test_has_elevated_permissions_manage_guild(self):
        """Test has_elevated_permissions returns True for manage_guild."""
        from discord import Member
        mock_member = Mock(spec=Member)
        mock_perms = Mock()
        mock_perms.administrator = False
        mock_perms.manage_guild = True
        mock_perms.moderate_members = False
        mock_member.guild_permissions = mock_perms
        
        result = has_elevated_permissions(mock_member)
        assert result is True

    def test_has_elevated_permissions_moderate_members(self):
        """Test has_elevated_permissions returns True for moderate_members."""
        from discord import Member
        mock_member = Mock(spec=Member)
        mock_perms = Mock()
        mock_perms.administrator = False
        mock_perms.manage_guild = False
        mock_perms.moderate_members = True
        mock_member.guild_permissions = mock_perms
        
        result = has_elevated_permissions(mock_member)
        assert result is True

    def test_has_elevated_permissions_no_elevated(self):
        """Test has_elevated_permissions returns False without elevated perms."""
        from discord import Member
        mock_member = Mock(spec=Member)
        mock_perms = Mock()
        mock_perms.administrator = False
        mock_perms.manage_guild = False
        mock_perms.moderate_members = False
        mock_member.guild_permissions = mock_perms
        
        result = has_elevated_permissions(mock_member)
        assert result is False

    def test_has_elevated_permissions_not_member(self):
        """Test has_elevated_permissions returns False for non-member."""
        from discord import User
        mock_user = Mock(spec=User)
        
        result = has_elevated_permissions(mock_user)
        assert result is False


class TestFormatDuration:
    """Tests for format_duration function."""

    def test_format_duration_zero(self):
        """Test format_duration for zero seconds."""
        result = format_duration(0)
        assert result == PERMANENT_DURATION

    def test_format_duration_seconds(self):
        """Test format_duration for seconds."""
        result = format_duration(30)
        assert result == "30 secs"

    def test_format_duration_minutes(self):
        """Test format_duration for minutes."""
        result = format_duration(300)
        assert result == "5 mins"

    def test_format_duration_single_hour(self):
        """Test format_duration for single hour."""
        result = format_duration(3600)
        assert result == "1 hour"

    def test_format_duration_multiple_hours(self):
        """Test format_duration for multiple hours."""
        result = format_duration(7200)
        assert result == "2 hours"

    def test_format_duration_single_day(self):
        """Test format_duration for single day."""
        result = format_duration(86400)
        assert result == "1 day"

    def test_format_duration_multiple_days(self):
        """Test format_duration for multiple days."""
        result = format_duration(259200)
        assert result == "3 days"

    def test_format_duration_weeks(self):
        """Test format_duration for weeks."""
        result = format_duration(604800)
        assert result == "7 days"
