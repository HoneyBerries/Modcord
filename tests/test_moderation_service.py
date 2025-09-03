"""
Tests for the moderation service.
"""

import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import discord

from src.bot.models.action import ActionType
from src.bot.services.moderation_service import ModerationService

class TestModerationService(unittest.IsolatedAsyncioTestCase):
    """
    Tests for the ModerationService class.
    """
    def setUp(self):
        """
        Set up the test case.
        """
        self.mock_bot = MagicMock()
        self.moderation_service = ModerationService(self.mock_bot)

    @patch('src.bot.services.moderation_service.send_dm_to_user', new_callable=AsyncMock)
    @patch('src.bot.services.moderation_service.create_punishment_embed', new_callable=AsyncMock)
    async def test_take_action_ban(self, mock_create_embed, mock_send_dm):
        """
        Tests the take_action method with a ban action.
        """
        mock_message = MagicMock(spec=discord.Message)
        mock_message.author = MagicMock(spec=discord.Member)
        mock_message.guild = MagicMock(spec=discord.Guild)
        mock_message.guild.ban = AsyncMock()
        mock_message.delete = AsyncMock()

        await self.moderation_service.take_action(ActionType.BAN, "Test ban reason", mock_message)

        mock_message.guild.ban.assert_called_once_with(mock_message.author, reason="AI Mod: Test ban reason")
        mock_send_dm.assert_called_once()
        mock_create_embed.assert_called_once()
        mock_message.delete.assert_called_once()

    @patch('src.bot.services.moderation_service.send_dm_to_user', new_callable=AsyncMock)
    @patch('src.bot.services.moderation_service.create_punishment_embed', new_callable=AsyncMock)
    async def test_take_action_warn(self, mock_create_embed, mock_send_dm):
        """
        Tests the take_action method with a warn action.
        """
        mock_message = MagicMock(spec=discord.Message)
        mock_message.author = MagicMock(spec=discord.Member)
        mock_message.guild = MagicMock(spec=discord.Guild)

        await self.moderation_service.take_action(ActionType.WARN, "Test warn reason", mock_message)

        mock_send_dm.assert_called_once()
        mock_create_embed.assert_called_once()

    async def test_take_action_delete(self):
        """
        Tests the take_action method with a delete action.
        """
        mock_message = MagicMock(spec=discord.Message)
        mock_message.author = MagicMock(spec=discord.Member)
        mock_message.guild = MagicMock(spec=discord.Guild)
        mock_message.delete = AsyncMock()

        await self.moderation_service.take_action(ActionType.DELETE, "Test delete reason", mock_message)

        mock_message.delete.assert_called_once()

if __name__ == "__main__":
    unittest.main()
