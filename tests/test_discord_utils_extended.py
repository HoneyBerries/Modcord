"""Extended tests for discord_utils module - utility functions."""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock, patch
import discord
from datetime import datetime, timezone, timedelta

from modcord.util.discord_utils import (
    create_punishment_embed,
    delete_recent_messages,
    delete_messages_background,
    DURATIONS,
)
from modcord.moderation.moderation_datatypes import ActionType


class TestCreatePunishmentEmbed:
    """Tests for create_punishment_embed function."""

    @pytest.mark.asyncio
    async def test_create_ban_embed(self):
        """Test creating ban punishment embed."""
        user = MagicMock(spec=discord.User)
        user.mention = "<@123>"
        user.id = 123
        
        embed = await create_punishment_embed(
            ActionType.BAN,
            user,
            "Spam",
            "1 day",
            bot_user=None
        )
        
        assert embed is not None
        assert isinstance(embed, discord.Embed)
        assert "Ban" in embed.title
        assert embed.color == discord.Color.red()

    @pytest.mark.asyncio
    async def test_create_kick_embed(self):
        """Test creating kick punishment embed."""
        user = MagicMock(spec=discord.User)
        user.mention = "<@123>"
        user.id = 123
        
        embed = await create_punishment_embed(
            ActionType.KICK,
            user,
            "Rule violation"
        )
        
        assert "Kick" in embed.title
        assert embed.color == discord.Color.orange()

    @pytest.mark.asyncio
    async def test_create_warn_embed(self):
        """Test creating warn punishment embed."""
        user = MagicMock(spec=discord.User)
        user.mention = "<@123>"
        user.id = 123
        
        embed = await create_punishment_embed(
            ActionType.WARN,
            user,
            "Minor issue"
        )
        
        assert "Warn" in embed.title
        assert embed.color == discord.Color.yellow()

    @pytest.mark.asyncio
    async def test_create_timeout_embed(self):
        """Test creating timeout punishment embed."""
        user = MagicMock(spec=discord.User)
        user.mention = "<@123>"
        user.id = 123
        
        embed = await create_punishment_embed(
            ActionType.TIMEOUT,
            user,
            "Harassment",
            "30 mins"
        )
        
        assert "Timeout" in embed.title
        assert embed.color == discord.Color.blue()

    @pytest.mark.asyncio
    async def test_create_delete_embed(self):
        """Test creating delete punishment embed."""
        user = MagicMock(spec=discord.User)
        user.mention = "<@123>"
        user.id = 123
        
        embed = await create_punishment_embed(
            ActionType.DELETE,
            user,
            "Inappropriate content"
        )
        
        assert "Delete" in embed.title

    @pytest.mark.asyncio
    async def test_create_unban_embed(self):
        """Test creating unban embed."""
        user = MagicMock(spec=discord.User)
        user.mention = "<@123>"
        user.id = 123
        
        embed = await create_punishment_embed(
            ActionType.UNBAN,
            user,
            "Ban expired"
        )
        
        assert "Unban" in embed.title
        assert embed.color == discord.Color.green()

    @pytest.mark.asyncio
    async def test_create_embed_with_issuer(self):
        """Test creating embed with issuer information."""
        user = MagicMock(spec=discord.User)
        user.mention = "<@123>"
        user.id = 123
        
        issuer = MagicMock(spec=discord.User)
        issuer.mention = "<@456>"
        
        embed = await create_punishment_embed(
            ActionType.WARN,
            user,
            "Test",
            issuer=issuer
        )
        
        # Check that moderator field exists
        field_names = [f.name for f in embed.fields]
        assert "Moderator" in field_names

    @pytest.mark.asyncio
    async def test_create_embed_with_duration(self):
        """Test creating embed with duration."""
        user = MagicMock(spec=discord.User)
        user.mention = "<@123>"
        user.id = 123
        
        embed = await create_punishment_embed(
            ActionType.BAN,
            user,
            "Test",
            "1 day"
        )
        
        field_names = [f.name for f in embed.fields]
        assert "Duration" in field_names

    @pytest.mark.asyncio
    async def test_create_embed_permanent_duration(self):
        """Test creating embed with permanent duration."""
        from modcord.util.discord_utils import PERMANENT_DURATION
        
        user = MagicMock(spec=discord.User)
        user.mention = "<@123>"
        user.id = 123
        
        embed = await create_punishment_embed(
            ActionType.BAN,
            user,
            "Test",
            PERMANENT_DURATION
        )
        
        field_names = [f.name for f in embed.fields]
        assert "Duration" in field_names

    @pytest.mark.asyncio
    async def test_create_embed_with_bot_user(self):
        """Test creating embed with bot user in footer."""
        user = MagicMock(spec=discord.User)
        user.mention = "<@123>"
        user.id = 123
        
        bot_user = MagicMock(spec=discord.ClientUser)
        bot_user.name = "ModBot"
        
        embed = await create_punishment_embed(
            ActionType.WARN,
            user,
            "Test",
            bot_user=bot_user
        )
        
        assert "ModBot" in embed.footer.text

    @pytest.mark.asyncio
    async def test_create_null_action_embed(self):
        """Test creating embed for null action."""
        user = MagicMock(spec=discord.User)
        user.mention = "<@123>"
        user.id = 123
        
        embed = await create_punishment_embed(
            ActionType.NULL,
            user,
            "No action"
        )
        
        assert "No Action" in embed.title


class TestDeleteRecentMessages:
    """Tests for delete_recent_messages function."""

    @pytest.mark.asyncio
    async def test_delete_recent_messages_zero_seconds(self):
        """Test with zero seconds returns 0."""
        guild = MagicMock()
        member = MagicMock()
        
        result = await delete_recent_messages(guild, member, 0)
        
        assert result == 0

    @pytest.mark.asyncio
    async def test_delete_recent_messages_negative_seconds(self):
        """Test with negative seconds returns 0."""
        guild = MagicMock()
        member = MagicMock()
        
        result = await delete_recent_messages(guild, member, -10)
        
        assert result == 0


class TestDeleteMessagesBackground:
    """Tests for delete_messages_background function."""

    @pytest.mark.asyncio
    async def test_delete_messages_background_success(self):
        """Test successful background message deletion."""
        ctx = AsyncMock()
        ctx.guild = MagicMock()
        ctx.followup.send = AsyncMock()
        
        user = MagicMock()
        user.mention = "<@123>"
        
        with patch('modcord.util.discord_utils.delete_recent_messages', new=AsyncMock(return_value=5)):
            await delete_messages_background(ctx, user, 60)
        
        ctx.followup.send.assert_called_once()
        call_args = ctx.followup.send.call_args
        assert "5" in call_args[0][0] or "5" in str(call_args)

    @pytest.mark.asyncio
    async def test_delete_messages_background_no_messages(self):
        """Test background deletion when no messages found."""
        ctx = AsyncMock()
        ctx.guild = MagicMock()
        ctx.followup.send = AsyncMock()
        
        user = MagicMock()
        user.mention = "<@123>"
        
        with patch('modcord.util.discord_utils.delete_recent_messages', new=AsyncMock(return_value=0)):
            await delete_messages_background(ctx, user, 60)
        
        ctx.followup.send.assert_called_once()
        call_args = ctx.followup.send.call_args
        assert "No recent messages" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_delete_messages_background_exception(self):
        """Test background deletion with exception."""
        ctx = AsyncMock()
        ctx.guild = MagicMock()
        ctx.followup.send = AsyncMock()
        
        user = MagicMock()
        
        with patch('modcord.util.discord_utils.delete_recent_messages', new=AsyncMock(side_effect=Exception("Error"))):
            await delete_messages_background(ctx, user, 60)
        
        ctx.followup.send.assert_called_once()
        call_args = ctx.followup.send.call_args
        assert "failed" in call_args[0][0].lower() or "⚠" in call_args[0][0]


