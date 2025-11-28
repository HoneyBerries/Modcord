"""Extended tests for discord_utils module - utility functions."""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock, patch
import discord
from datetime import datetime, timezone, timedelta

from modcord.moderation.moderation_embed import create_punishment_embed
from modcord.util.discord_utils import (
    delete_recent_messages,
    delete_messages_background,
    DURATIONS,
)
from modcord.datatypes.action_datatypes import ActionType


class TestCreatePunishmentEmbed:
    """Tests for create_punishment_embed function."""

    @pytest.mark.asyncio
    async def test_create_ban_embed(self):
        """Test creating ban punishment embed."""
        user = MagicMock(spec=discord.Member)
        user.mention = "<@123>"
        user.id = 123
        user.name = "testuser"
        
        guild = MagicMock(spec=discord.Guild)
        guild.name = "Test Guild"
        
        embed = await create_punishment_embed(
            ActionType.BAN,
            user,
            guild,
            "Spam"
        )
        
        assert embed is not None
        assert isinstance(embed, discord.Embed)
        assert "BAN" in embed.title
        assert embed.color == discord.Color.red()

    @pytest.mark.asyncio
    async def test_create_kick_embed(self):
        """Test creating kick punishment embed."""
        user = MagicMock(spec=discord.Member)
        user.mention = "<@123>"
        user.id = 123
        user.name = "testuser"
        
        guild = MagicMock(spec=discord.Guild)
        guild.name = "Test Guild"
        
        embed = await create_punishment_embed(
            ActionType.KICK,
            user,
            guild,
            "Rule violation"
        )
        
        assert "KICK" in embed.title
        assert embed.color == discord.Color.red()

    @pytest.mark.asyncio
    async def test_create_warn_embed(self):
        """Test creating warn punishment embed."""
        user = MagicMock(spec=discord.Member)
        user.mention = "<@123>"
        user.id = 123
        user.name = "testuser"
        
        guild = MagicMock(spec=discord.Guild)
        guild.name = "Test Guild"
        
        embed = await create_punishment_embed(
            ActionType.WARN,
            user,
            guild,
            "Minor issue"
        )
        
        assert "WARN" in embed.title
        assert embed.color == discord.Color.red()

    @pytest.mark.asyncio
    async def test_create_timeout_embed(self):
        """Test creating timeout punishment embed."""
        user = MagicMock(spec=discord.Member)
        user.mention = "<@123>"
        user.id = 123
        user.name = "testuser"
        
        guild = MagicMock(spec=discord.Guild)
        guild.name = "Test Guild"
        
        embed = await create_punishment_embed(
            ActionType.TIMEOUT,
            user,
            guild,
            "Harassment"
        )
        
        assert "TIMEOUT" in embed.title
        assert embed.color == discord.Color.red()

    @pytest.mark.asyncio
    async def test_create_delete_embed(self):
        """Test creating delete punishment embed."""
        user = MagicMock(spec=discord.Member)
        user.mention = "<@123>"
        user.id = 123
        user.name = "testuser"
        
        guild = MagicMock(spec=discord.Guild)
        guild.name = "Test Guild"
        
        embed = await create_punishment_embed(
            ActionType.DELETE,
            user,
            guild,
            "Inappropriate content"
        )
        
        assert "DELETE" in embed.title

    @pytest.mark.asyncio
    async def test_create_embed_with_duration(self):
        """Test creating embed with duration."""
        user = MagicMock(spec=discord.Member)
        user.mention = "<@123>"
        user.id = 123
        user.name = "testuser"
        
        guild = MagicMock(spec=discord.Guild)
        guild.name = "Test Guild"
        
        duration = timedelta(hours=1)
        embed = await create_punishment_embed(
            ActionType.BAN,
            user,
            guild,
            "Test",
            duration=duration
        )
        
        field_names = [f.name for f in embed.fields]
        assert "Duration" in field_names

    @pytest.mark.asyncio
    async def test_footer_contains_modcord(self):
        """Test that footer contains ModCord text."""
        user = MagicMock(spec=discord.Member)
        user.mention = "<@123>"
        user.id = 123
        user.name = "testuser"
        
        guild = MagicMock(spec=discord.Guild)
        guild.name = "Test Guild"
        
        embed = await create_punishment_embed(
            ActionType.WARN,
            user,
            guild,
            "Test"
        )
        
        assert "ModCord" in embed.footer.text


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


