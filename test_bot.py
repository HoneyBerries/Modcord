import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from actions import ActionType
import discord
import ai_model

class TestBot(unittest.IsolatedAsyncioTestCase):
    @patch.object(ai_model, 'init_ai_model', return_value=(None, None, None))
    async def test_on_message_action(self):
        with patch('bot.ai.get_appropriate_action', new_callable=AsyncMock) as mock_get_appropriate_action, \
             patch('bot.bot_helper.take_action', new_callable=AsyncMock) as mock_take_action:
            # Mock the AI model to return a specific action
            mock_get_appropriate_action.return_value = (ActionType.BAN, "Test reason")

            # Create a mock message
            message = MagicMock(spec=discord.Message)
            message.author.bot = False
            message.author.guild_permissions.administrator = False
            message.clean_content = "Test message"
            message.guild.id = 123
            message.channel.id = 456
            message.author.name = "testuser"

            # Run the on_message event handler
            from bot import on_message
            await on_message(message)

            # Check if the AI model was called with the correct arguments
            mock_get_appropriate_action.assert_called_once()
            mock_take_action.assert_called_once()

if __name__ == "__main__":
    unittest.main()
