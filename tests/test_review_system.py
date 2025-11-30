"""
Tests for the human moderator review system.

This module tests:
- HumanReviewManager batch consolidation
- Review database operations
- HumanReviewResolutionView button interactions
- Integration with moderation pipeline
"""

import pytest
import discord
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
import uuid

from modcord.moderation.human_review_manager import HumanReviewManager
from modcord.datatypes.action_datatypes import ActionData, ActionType
from modcord.datatypes.discord_datatypes import ChannelID, UserID, DiscordUsername, GuildID, MessageID
from modcord.datatypes.moderation_datatypes import ModerationMessage, ModerationUser
from modcord.database.database import get_db


@pytest.fixture
async def test_db():
    """Initialize test database."""
    await get_db().initialize()
    yield
    # Cleanup
    get_db().shutdown()


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
    message.created_at = datetime.now(timezone.utc)
    
    # Mock channel
    channel = MagicMock(spec=discord.TextChannel)
    channel.mention = "<#123456>"
    channel.id = 123456
    message.channel = channel
    
    return message


@pytest.fixture
def mock_guild_settings():
    """Create mock guild settings."""
    from modcord.datatypes.guild_settings import GuildSettings
    settings = GuildSettings(guild_id=987654321)
    settings.review_channel_ids = [555666777]
    settings.moderator_role_ids = [888999000]
    return settings


def build_moderation_entities(member, message, guild):
    """Helper to build ModerationUser and ModerationMessage for tests."""
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    channel_id = ChannelID(message.channel.id) if hasattr(message.channel, "id") else None

    pivot_message = ModerationMessage(
        message_id=MessageID(message.id),
        user_id=UserID.from_int(member.id),
        content=message.content,
        timestamp=timestamp,
        guild_id=GuildID.from_int(guild.id),
        channel_id=channel_id,
        discord_message=message,
    )

    moderation_user = ModerationUser(
        user_id=UserID.from_int(member.id),
        username=DiscordUsername(member.display_name),
        roles=[],
        join_date=None,
        messages=[pivot_message],
        past_actions=[],
    )

    return moderation_user, pivot_message


class TestHumanReviewManager:
    """Tests for HumanReviewManager."""
    
    @pytest.mark.asyncio
    async def test_add_item_for_review(self, test_db, mock_bot, mock_guild, mock_member, mock_message):
        """Test adding a review item to the batch."""
        manager = HumanReviewManager(mock_bot)
        action = ActionData(
            user_id=UserID("111222333"),
            action=ActionType.REVIEW,
            reason="Spam detected by AI",
            timeout_duration=0,
            ban_duration=0
        )
        
        review_user, pivot_message = build_moderation_entities(mock_member, mock_message, mock_guild)

        await manager.add_item_for_review(
            guild=mock_guild,
            user=review_user,
            action=action
        )
        
        # Verify item was added to batch (now dict keyed by user_id)
        assert mock_guild.id in manager._active_batches
        assert len(manager._active_batches[mock_guild.id]) == 1
        
        review_item = manager._active_batches[mock_guild.id]["111222333"]
        assert review_item.user == review_user
        assert review_item.action.reason == "Spam detected by AI"
    
    @pytest.mark.asyncio
    async def test_multiple_review_items_same_guild(self, test_db, mock_bot, mock_guild):
        """Test adding multiple review items to the same guild."""
        manager = HumanReviewManager(mock_bot)
        
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
            message.created_at = datetime.now(timezone.utc)
            message.channel = MagicMock()
            message.channel.mention = f"<#{i}>"
            message.channel.id = 9000 + i
            
            action = ActionData(
                user_id=UserID(str(100000 + i)),
                action=ActionType.REVIEW,
                reason=f"Reason {i}",
                timeout_duration=0,
                ban_duration=0
            )

            review_user, pivot_message = build_moderation_entities(member, message, mock_guild)
            await manager.add_item_for_review(
                guild=mock_guild,
                user=review_user,
                action=action
            )
        
        # Verify all items are in the same batch
        assert mock_guild.id in manager._active_batches
        assert len(manager._active_batches[mock_guild.id]) == 3
    
    @pytest.mark.asyncio
    async def test_send_review_embed(self, test_db, mock_bot, mock_guild, mock_guild_settings):
        """Test finalizing a review batch sends consolidated embed."""
        manager = HumanReviewManager(mock_bot)
        
        # Mock review channel
        review_channel = MagicMock(spec=discord.TextChannel)
        review_channel.id = 555666777
        mock_sent_message = MagicMock()
        mock_sent_message.id = 999888777
        review_channel.send = AsyncMock(return_value=mock_sent_message)
        
        mock_guild.get_channel = MagicMock(return_value=review_channel)
        mock_guild.get_role = MagicMock(return_value=None)
        
        # Add review items
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
            message.created_at = datetime.now(timezone.utc)
            message.channel = MagicMock()
            message.channel.mention = f"<#{i}>"
            message.channel.id = 8000 + i
            
            action = ActionData(
                user_id=UserID(str(100000 + i)),
                action=ActionType.REVIEW,
                reason=f"Reason {i}",
                timeout_duration=0,
                ban_duration=0
            )

            review_user, pivot_message = build_moderation_entities(member, message, mock_guild)
            await manager.add_item_for_review(
                guild=mock_guild,
                user=review_user,
                action=action
            )
        
        # Finalize the batch
        with patch('modcord.bot.review_ui.HumanReviewResolutionView'):
            result = await manager.send_review_embed(mock_guild, mock_guild_settings)
        
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
        manager = HumanReviewManager(mock_bot)
        result = await manager.send_review_embed(mock_guild, mock_guild_settings)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_build_role_mentions(self, test_db, mock_bot, mock_guild, mock_guild_settings):
        """Test building moderator role mentions."""
        from modcord.ui.review_embed_helper import build_role_mentions
        
        # Mock role
        mock_role = MagicMock()
        mock_role.mention = "<@&888999000>"
        mock_guild.get_role = MagicMock(return_value=mock_role)
        
        mentions = build_role_mentions(mock_guild, mock_guild_settings)
        assert mentions == "<@&888999000>"
    
    @pytest.mark.asyncio
    async def test_build_role_mentions_no_roles(self, test_db, mock_bot, mock_guild):
        """Test building role mentions with no configured roles."""
        from modcord.ui.review_embed_helper import build_role_mentions
        
        from modcord.datatypes.guild_settings import GuildSettings
        settings = GuildSettings(guild_id=987654321)
        settings.moderator_role_ids = []
        
        mentions = build_role_mentions(mock_guild, settings)
        assert mentions is None


class TestReviewUI:
    """Tests for HumanReviewResolutionView."""
    
    @pytest.mark.asyncio
    async def test_resolve_button_permission_check(self):
        """Test that resolve button checks moderator permissions."""
        from modcord.ui.review_ui import HumanReviewResolutionView
        
        batch_id = str(uuid.uuid4())
        guild_id = 987654321
        
        view = HumanReviewResolutionView(batch_id=batch_id, guild_id=guild_id)
        
        # Mock interaction without permissions
        interaction = MagicMock(spec=discord.Interaction)
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.guild_permissions.manage_guild = False
        interaction.user.roles = []
        interaction.response.send_message = AsyncMock()
        
        with patch('modcord.util.discord_utils.has_review_permission', return_value=False):
            # Call the button's callback directly
            resolve_button = view.children[0]
            await resolve_button.callback(interaction)
        
        # Verify permission denied message was sent
        interaction.response.send_message.assert_called_once()
        call_args = interaction.response.send_message.call_args
        assert "don't have permission" in call_args[0][0]
    
    @pytest.mark.asyncio
    async def test_command_suggestion_buttons(self):
        """Test that quick-action buttons send command suggestions."""
        from modcord.ui.review_ui import HumanReviewResolutionView
        
        batch_id = str(uuid.uuid4())
        guild_id = 987654321
        
        view = HumanReviewResolutionView(batch_id=batch_id, guild_id=guild_id)
        
        # Mock interaction
        interaction = MagicMock(spec=discord.Interaction)
        interaction.user = MagicMock()
        interaction.user.id = 123456
        interaction.response.send_message = AsyncMock()
        
        # Test warn button - get the button and call its callback directly
        warn_button = view.children[1]
        await warn_button.callback(interaction)
        interaction.response.send_message.assert_called_once()
        call_args = interaction.response.send_message.call_args[0][0]
        assert "/warn" in call_args
        assert "ephemeral" in str(interaction.response.send_message.call_args)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
