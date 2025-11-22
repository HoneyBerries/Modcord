"""
Tests for the human moderator review system.

This module tests:
- ReviewNotificationManager batch consolidation
- Review database operations
- ReviewResolutionView button interactions
- Integration with moderation pipeline
"""

import pytest
import discord
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
import uuid

from modcord.moderation.review_notifications import ReviewNotificationManager, ReviewItem
from modcord.moderation.moderation_datatypes import ActionData, ActionType
from modcord.database.database import init_database, get_connection


@pytest.fixture
async def test_db():
    """Initialize test database."""
    await init_database()
    yield
    # Cleanup happens automatically with test database


@pytest.fixture
def mock_bot():
    """Create a mock Discord bot."""
    bot = MagicMock(spec=discord.Bot)
    bot.user = MagicMock()
    bot.user.name = "TestBot"
    bot.user.id = 123456789
    return bot


@pytest.fixture
def mock_guild():
    """Create a mock Discord guild."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = 987654321
    guild.name = "Test Guild"
    return guild


@pytest.fixture
def mock_member():
    """Create a mock Discord member."""
    member = MagicMock(spec=discord.Member)
    member.id = 111222333
    member.display_name = "TestUser"
    member.mention = "<@111222333>"
    return member


@pytest.fixture
def mock_message():
    """Create a mock Discord message."""
    message = MagicMock(spec=discord.Message)
    message.id = 444555666
    message.content = "Test message content"
    message.jump_url = "https://discord.com/channels/987654321/123456/444555666"
    message.attachments = []
    
    # Mock channel
    channel = MagicMock(spec=discord.TextChannel)
    channel.mention = "<#123456>"
    message.channel = channel
    
    return message


@pytest.fixture
def mock_guild_settings():
    """Create mock guild settings."""
    from modcord.configuration.guild_settings import GuildSettings
    settings = GuildSettings(guild_id=987654321)
    settings.review_channel_ids = [555666777]
    settings.moderator_role_ids = [888999000]
    return settings


class TestReviewNotificationManager:
    """Tests for ReviewNotificationManager."""
    
    @pytest.mark.asyncio
    async def test_add_review_item(self, test_db, mock_bot, mock_guild, mock_member, mock_message):
        """Test adding a review item to the batch."""
        manager = ReviewNotificationManager(mock_bot)
        action = ActionData(
            user_id="111222333",
            action=ActionType.REVIEW,
            reason="Spam detected by AI",
            timeout_duration=0,
            ban_duration=0
        )
        
        with patch('modcord.moderation.review_notifications.get_past_actions', new_callable=AsyncMock) as mock_past:
            mock_past.return_value = []
            
            await manager.add_review_item(
                guild=mock_guild,
                user=mock_member,
                message=mock_message,
                action=action
            )
        
        # Verify item was added to batch
        assert mock_guild.id in manager._active_batches
        assert len(manager._active_batches[mock_guild.id]) == 1
        
        review_item = manager._active_batches[mock_guild.id][0]
        assert review_item.user == mock_member
        assert review_item.reason == "Spam detected by AI"
        assert review_item.message == mock_message
    
    @pytest.mark.asyncio
    async def test_multiple_review_items_same_guild(self, test_db, mock_bot, mock_guild):
        """Test adding multiple review items to the same guild."""
        manager = ReviewNotificationManager(mock_bot)
        
        with patch('modcord.moderation.review_notifications.get_past_actions', new_callable=AsyncMock) as mock_past:
            mock_past.return_value = []
            
            # Add three review items
            for i in range(3):
                member = MagicMock(spec=discord.Member)
                member.id = 100000 + i
                member.display_name = f"User{i}"
                member.mention = f"<@{100000 + i}>"
                
                message = MagicMock(spec=discord.Message)
                message.id = 200000 + i
                message.content = f"Message {i}"
                message.jump_url = f"https://discord.com/test/{i}"
                message.attachments = []
                message.channel = MagicMock()
                message.channel.mention = f"<#{i}>"
                
                action = ActionData(
                    user_id=str(100000 + i),
                    action=ActionType.REVIEW,
                    reason=f"Reason {i}",
                    timeout_duration=0,
                    ban_duration=0
                )
                
                await manager.add_review_item(
                    guild=mock_guild,
                    user=member,
                    message=message,
                    action=action
                )
        
        # Verify all items are in the same batch
        assert mock_guild.id in manager._active_batches
        assert len(manager._active_batches[mock_guild.id]) == 3
    
    @pytest.mark.asyncio
    async def test_finalize_batch(self, test_db, mock_bot, mock_guild, mock_guild_settings):
        """Test finalizing a review batch sends consolidated embed."""
        manager = ReviewNotificationManager(mock_bot)
        
        # Mock review channel
        review_channel = MagicMock(spec=discord.TextChannel)
        review_channel.id = 555666777
        mock_sent_message = MagicMock()
        mock_sent_message.id = 999888777
        review_channel.send = AsyncMock(return_value=mock_sent_message)
        
        mock_guild.get_channel = MagicMock(return_value=review_channel)
        mock_guild.get_role = MagicMock(return_value=None)
        
        # Add review items
        with patch('modcord.moderation.review_notifications.get_past_actions', new_callable=AsyncMock) as mock_past:
            mock_past.return_value = []
            
            for i in range(2):
                member = MagicMock(spec=discord.Member)
                member.id = 100000 + i
                member.display_name = f"User{i}"
                member.mention = f"<@{100000 + i}>"
                
                message = MagicMock(spec=discord.Message)
                message.id = 200000 + i
                message.content = f"Message {i}"
                message.jump_url = f"https://discord.com/test/{i}"
                message.attachments = []
                message.channel = MagicMock()
                message.channel.mention = f"<#{i}>"
                
                action = ActionData(
                    user_id=str(100000 + i),
                    action=ActionType.REVIEW,
                    reason=f"Reason {i}",
                    timeout_duration=0,
                    ban_duration=0
                )
                
                await manager.add_review_item(
                    guild=mock_guild,
                    user=member,
                    message=message,
                    action=action
                )
        
        # Finalize the batch
        with patch('modcord.moderation.review_notifications.ReviewResolutionView'):
            result = await manager.finalize_batch(mock_guild, mock_guild_settings)
        
        # Verify batch was sent
        assert result is True
        review_channel.send.assert_called_once()
        
        # Verify embed was created with consolidated data
        call_kwargs = review_channel.send.call_args.kwargs
        assert 'embed' in call_kwargs
        embed = call_kwargs['embed']
        assert embed.title == "🛡️ AI Moderation Review Request"
        assert "2 user(s)" in embed.description
        assert len(embed.fields) == 2  # Two users
        
        # Verify batch was cleared
        assert mock_guild.id not in manager._active_batches
    
    @pytest.mark.asyncio
    async def test_finalize_empty_batch(self, test_db, mock_bot, mock_guild, mock_guild_settings):
        """Test finalizing an empty batch returns False."""
        manager = ReviewNotificationManager(mock_bot)
        result = await manager.finalize_batch(mock_guild, mock_guild_settings)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_build_role_mentions(self, test_db, mock_bot, mock_guild, mock_guild_settings):
        """Test building moderator role mentions."""
        manager = ReviewNotificationManager(mock_bot)
        
        # Mock role
        mock_role = MagicMock()
        mock_role.mention = "<@&888999000>"
        mock_guild.get_role = MagicMock(return_value=mock_role)
        
        mentions = manager._build_role_mentions(mock_guild, mock_guild_settings)
        assert mentions == "<@&888999000>"
    
    @pytest.mark.asyncio
    async def test_build_role_mentions_no_roles(self, test_db, mock_bot, mock_guild):
        """Test building role mentions with no configured roles."""
        manager = ReviewNotificationManager(mock_bot)
        
        from modcord.configuration.guild_settings import GuildSettings
        settings = GuildSettings(guild_id=987654321)
        settings.moderator_role_ids = []
        
        mentions = manager._build_role_mentions(mock_guild, settings)
        assert mentions is None


class TestReviewDatabase:
    """Tests for review database operations."""
    
    @pytest.mark.asyncio
    async def test_store_review_request(self, test_db):
        """Test storing a review request in the database."""
        batch_id = str(uuid.uuid4())
        guild_id = 987654321
        channel_id = 555666777
        message_id = 999888777
        
        # First ensure guild_settings exists
        async with get_connection() as db:
            await db.execute(
                "INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)",
                (guild_id,)
            )
            await db.commit()
        
        manager = ReviewNotificationManager(MagicMock())
        await manager._store_review_request(batch_id, guild_id, channel_id, message_id)
        
        # Verify it was stored
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT batch_id, guild_id, channel_id, message_id, status FROM review_requests WHERE batch_id = ?",
                (batch_id,)
            )
            row = await cursor.fetchone()
        
        assert row is not None
        assert row[0] == batch_id
        assert row[1] == guild_id
        assert row[2] == channel_id
        assert row[3] == message_id
        assert row[4] == "pending"
    
    @pytest.mark.asyncio
    async def test_mark_resolved(self, test_db):
        """Test marking a review as resolved."""
        batch_id = str(uuid.uuid4())
        guild_id = 987654321
        resolved_by = 111222333
        
        # First ensure guild_settings exists
        async with get_connection() as db:
            await db.execute(
                "INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)",
                (guild_id,)
            )
            await db.commit()
        
        # Store a review request
        async with get_connection() as db:
            await db.execute(
                "INSERT INTO review_requests (batch_id, guild_id, channel_id, status) VALUES (?, ?, ?, 'pending')",
                (batch_id, guild_id, 555666777)
            )
            await db.commit()
        
        # Mark as resolved
        result = await ReviewNotificationManager.mark_resolved(
            batch_id=batch_id,
            resolved_by=resolved_by,
            resolution_note="Test resolution"
        )
        
        assert result is True
        
        # Verify status was updated
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT status, resolved_by, resolution_note FROM review_requests WHERE batch_id = ?",
                (batch_id,)
            )
            row = await cursor.fetchone()
        
        assert row[0] == "resolved"
        assert row[1] == resolved_by
        assert row[2] == "Test resolution"
    
    @pytest.mark.asyncio
    async def test_mark_resolved_nonexistent(self, test_db):
        """Test marking a nonexistent review as resolved returns False."""
        result = await ReviewNotificationManager.mark_resolved(
            batch_id="nonexistent-batch-id",
            resolved_by=123456,
            resolution_note="Test"
        )
        assert result is False
    
    @pytest.mark.asyncio
    async def test_get_review_status(self, test_db):
        """Test getting review status."""
        batch_id = str(uuid.uuid4())
        guild_id = 987654321
        
        # First ensure guild_settings exists
        async with get_connection() as db:
            await db.execute(
                "INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)",
                (guild_id,)
            )
            await db.commit()
        
        # Store a review request
        async with get_connection() as db:
            await db.execute(
                "INSERT INTO review_requests (batch_id, guild_id, channel_id, status) VALUES (?, ?, ?, 'pending')",
                (batch_id, guild_id, 555666777)
            )
            await db.commit()
        
        # Get status
        status = await ReviewNotificationManager.get_review_status(batch_id)
        
        assert status is not None
        assert status["status"] == "pending"
        assert status["resolved_by"] is None
        assert status["resolved_at"] is None
    
    @pytest.mark.asyncio
    async def test_get_review_status_nonexistent(self, test_db):
        """Test getting status of nonexistent review returns None."""
        status = await ReviewNotificationManager.get_review_status("nonexistent-batch-id")
        assert status is None


class TestReviewUI:
    """Tests for ReviewResolutionView."""
    
    @pytest.mark.asyncio
    async def test_resolve_button_permission_check(self):
        """Test that resolve button checks moderator permissions."""
        from modcord.bot.review_ui import ReviewResolutionView
        
        batch_id = str(uuid.uuid4())
        guild_id = 987654321
        
        view = ReviewResolutionView(batch_id=batch_id, guild_id=guild_id)
        
        # Mock interaction without permissions
        interaction = MagicMock(spec=discord.Interaction)
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.guild_permissions.manage_guild = False
        interaction.user.roles = []
        interaction.response.send_message = AsyncMock()
        
        with patch.object(view, '_check_moderator_permission', return_value=False):
            await view.resolve_button(view.children[0], interaction)
        
        # Verify permission denied message was sent
        interaction.response.send_message.assert_called_once()
        call_args = interaction.response.send_message.call_args
        assert "don't have permission" in call_args[0][0]
    
    @pytest.mark.asyncio
    async def test_command_suggestion_buttons(self):
        """Test that quick-action buttons send command suggestions."""
        from modcord.bot.review_ui import ReviewResolutionView
        
        batch_id = str(uuid.uuid4())
        guild_id = 987654321
        
        view = ReviewResolutionView(batch_id=batch_id, guild_id=guild_id)
        
        # Mock interaction
        interaction = MagicMock(spec=discord.Interaction)
        interaction.user = MagicMock()
        interaction.user.id = 123456
        interaction.response.send_message = AsyncMock()
        
        # Test warn button
        await view.warn_button(view.children[1], interaction)
        interaction.response.send_message.assert_called_once()
        call_args = interaction.response.send_message.call_args[0][0]
        assert "/warn" in call_args
        assert "ephemeral" in str(interaction.response.send_message.call_args)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
