"""Additional tests for discord_utils async functions."""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock, patch
import discord
from datetime import datetime, timezone

from modcord.util.discord_utils import (
    safe_delete_message,
    send_dm_to_user,
    has_permissions,
    iter_moderatable_channels,
    delete_messages_by_ids,
    delete_recent_messages_by_count,
)


class TestSafeDeleteMessage:
    """Tests for safe_delete_message async function."""

    @pytest.mark.asyncio
    async def test_safe_delete_success(self):
        """Test successful message deletion."""
        message = AsyncMock()
        message.delete = AsyncMock()
        
        result = await safe_delete_message(message)
        
        assert result is True
        message.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_safe_delete_not_found(self):
        """Test deletion of already deleted message."""
        message = AsyncMock()
        response = MagicMock()
        response.status = 404
        response.reason = "Not Found"
        message.delete.side_effect = discord.NotFound(response, "message")
        
        result = await safe_delete_message(message)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_safe_delete_forbidden(self):
        """Test deletion without permissions."""
        message = AsyncMock()
        response = MagicMock()
        response.status = 403
        response.reason = "Forbidden"
        message.delete.side_effect = discord.Forbidden(response, "message")
        
        result = await safe_delete_message(message)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_safe_delete_exception(self):
        """Test deletion with generic exception."""
        message = AsyncMock()
        message.delete.side_effect = Exception("Unknown error")
        
        result = await safe_delete_message(message)
        
        assert result is False


class TestSendDmToUser:
    """Tests for send_dm_to_user async function."""

    @pytest.mark.asyncio
    async def test_send_dm_success(self):
        """Test successful DM sending."""
        user = AsyncMock()
        user.send = AsyncMock()
        
        result = await send_dm_to_user(user, "Test message")
        
        assert result is True
        user.send.assert_called_once_with("Test message")

    @pytest.mark.asyncio
    async def test_send_dm_forbidden(self):
        """Test DM sending when DMs are disabled."""
        user = AsyncMock()
        response = MagicMock()
        response.status = 403
        response.reason = "Forbidden"
        user.send.side_effect = discord.Forbidden(response, "message")
        user.display_name = "TestUser"
        
        result = await send_dm_to_user(user, "Test message")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_send_dm_exception(self):
        """Test DM sending with generic exception."""
        user = AsyncMock()
        user.send.side_effect = Exception("Network error")
        user.display_name = "TestUser"
        
        result = await send_dm_to_user(user, "Test message")
        
        assert result is False


class TestHasPermissions:
    """Tests for has_permissions function."""

    def test_has_permissions_with_all(self):
        """Test when user has all required permissions."""
        ctx = MagicMock()
        ctx.author = MagicMock(spec=discord.Member)
        ctx.author.guild_permissions.ban_members = True
        ctx.author.guild_permissions.kick_members = True
        
        result = has_permissions(ctx, ban_members=True, kick_members=True)
        
        assert result is True

    def test_has_permissions_missing_one(self):
        """Test when user is missing one permission."""
        ctx = MagicMock()
        ctx.author = MagicMock(spec=discord.Member)
        ctx.author.guild_permissions.ban_members = True
        ctx.author.guild_permissions.kick_members = False
        
        result = has_permissions(ctx, ban_members=True, kick_members=True)
        
        assert result is False

    def test_has_permissions_non_member(self):
        """Test when author is not a Member."""
        ctx = MagicMock()
        ctx.author = MagicMock(spec=discord.User)
        
        result = has_permissions(ctx, ban_members=True)
        
        assert result is False

    def test_has_permissions_single_permission(self):
        """Test checking a single permission."""
        ctx = MagicMock()
        ctx.author = MagicMock(spec=discord.Member)
        ctx.author.guild_permissions.manage_messages = True
        
        result = has_permissions(ctx, manage_messages=True)
        
        assert result is True


class TestIterModeratableChannels:
    """Tests for iter_moderatable_channels function."""

    def test_iter_moderatable_channels_all_valid(self):
        """Test iterating channels when all are moderatable."""
        guild = MagicMock()
        channel1 = MagicMock(spec=discord.TextChannel)
        channel2 = MagicMock(spec=discord.TextChannel)
        guild.text_channels = [channel1, channel2]
        guild.me = MagicMock()
        
        # Mock permissions
        permissions = MagicMock()
        permissions.read_messages = True
        permissions.manage_messages = True
        channel1.permissions_for.return_value = permissions
        channel2.permissions_for.return_value = permissions
        
        channels = list(iter_moderatable_channels(guild))
        
        assert len(channels) == 2

    def test_iter_moderatable_channels_some_invalid(self):
        """Test iterating when some channels lack permissions."""
        guild = MagicMock()
        channel1 = MagicMock(spec=discord.TextChannel)
        channel2 = MagicMock(spec=discord.TextChannel)
        guild.text_channels = [channel1, channel2]
        guild.me = MagicMock()
        
        # Channel 1 has permissions, channel 2 doesn't
        perm1 = MagicMock()
        perm1.read_messages = True
        perm1.manage_messages = True
        perm2 = MagicMock()
        perm2.read_messages = False
        perm2.manage_messages = True
        
        channel1.permissions_for.return_value = perm1
        channel2.permissions_for.return_value = perm2
        
        channels = list(iter_moderatable_channels(guild))
        
        assert len(channels) == 1

    def test_iter_moderatable_channels_empty(self):
        """Test with no text channels."""
        guild = MagicMock()
        guild.text_channels = []
        
        channels = list(iter_moderatable_channels(guild))
        
        assert len(channels) == 0


class TestDeleteMessagesByIds:
    """Tests for delete_messages_by_ids async function."""

    @pytest.mark.asyncio
    async def test_delete_messages_by_ids_success(self):
        """Test successful deletion of messages by IDs."""
        guild = MagicMock()
        channel = AsyncMock(spec=discord.TextChannel)
        guild.text_channels = [channel]
        guild.me = MagicMock()
        
        # Mock permissions
        permissions = MagicMock()
        permissions.read_messages = True
        permissions.manage_messages = True
        channel.permissions_for.return_value = permissions
        
        # Mock message
        message = AsyncMock()
        message.delete = AsyncMock()
        channel.fetch_message = AsyncMock(return_value=message)
        
        result = await delete_messages_by_ids(guild, ["123"])
        
        assert result == 1

    @pytest.mark.asyncio
    async def test_delete_messages_by_ids_empty(self):
        """Test with empty message ID list."""
        guild = MagicMock()
        
        result = await delete_messages_by_ids(guild, [])
        
        assert result == 0

    @pytest.mark.asyncio
    async def test_delete_messages_by_ids_not_found(self):
        """Test when messages are not found."""
        guild = MagicMock()
        channel = AsyncMock(spec=discord.TextChannel)
        guild.text_channels = [channel]
        guild.me = MagicMock()
        
        permissions = MagicMock()
        permissions.read_messages = True
        permissions.manage_messages = True
        channel.permissions_for.return_value = permissions
        
        response = MagicMock()
        response.status = 404
        response.reason = "Not Found"
        channel.fetch_message = AsyncMock(side_effect=discord.NotFound(response, "message"))
        
        result = await delete_messages_by_ids(guild, ["123"])
        
        assert result == 0

    @pytest.mark.asyncio
    async def test_delete_messages_by_ids_invalid_id(self):
        """Test with invalid message ID."""
        guild = MagicMock()
        guild.text_channels = []
        
        result = await delete_messages_by_ids(guild, ["invalid"])
        
        assert result == 0


class TestDeleteRecentMessagesByCount:
    """Tests for delete_recent_messages_by_count async function."""

    @pytest.mark.asyncio
    async def test_delete_recent_messages_by_count_zero(self):
        """Test with count of zero."""
        guild = MagicMock()
        member = MagicMock()
        
        result = await delete_recent_messages_by_count(guild, member, 0)
        
        assert result == 0

    @pytest.mark.asyncio
    async def test_delete_recent_messages_by_count_success(self):
        """Test successful deletion by count."""
        guild = MagicMock()
        member = MagicMock()
        member.id = 123
        
        channel = AsyncMock(spec=discord.TextChannel)
        guild.text_channels = [channel]
        guild.me = MagicMock()
        
        permissions = MagicMock()
        permissions.read_messages = True
        permissions.manage_messages = True
        channel.permissions_for.return_value = permissions
        
        # Mock messages
        message1 = AsyncMock()
        message1.author = member
        message1.delete = AsyncMock()
        
        async def mock_history(limit):
            yield message1
        
        channel.history = mock_history
        
        result = await delete_recent_messages_by_count(guild, member, 1)
        
        assert result == 1
