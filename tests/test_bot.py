import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from actions import ActionType
import discord

@patch('ai_model.get_model', return_value=(MagicMock(), MagicMock(), "System Prompt Template: {SERVER_RULES}"))
class TestBotEvents(unittest.IsolatedAsyncioTestCase):

    @patch('ai_model.get_appropriate_action', new_callable=AsyncMock)
    @patch('bot_helper.take_action', new_callable=AsyncMock)
    async def test_on_message_moderation_action(self, mock_take_action, mock_get_appropriate_action, mock_get_model):
        """
        Test that the on_message event triggers a moderation action when the AI returns a non-null action.
        """
        from cogs.events import EventsCog

        # Mock the AI model to return a ban action
        mock_get_appropriate_action.return_value = (ActionType.BAN, "User was spamming")

        # Create a mock bot and cog
        mock_bot = MagicMock()
        cog = EventsCog(mock_bot)

        # Create a mock message
        message = MagicMock(spec=discord.Message)
        message.author.bot = False
        message.author.guild_permissions.administrator = False
        message.clean_content = "This is a test message that should trigger a ban."
        message.guild.id = 123
        message.channel.id = 456
        message.author.name = "testuser"

        # Call the on_message event handler
        await cog.on_message(message)

        # Assert that the AI action was called and the moderation action was taken
        mock_get_appropriate_action.assert_called_once()
        mock_take_action.assert_called_once_with(ActionType.BAN, "User was spamming", message, mock_bot.user)

    @patch('ai_model.get_appropriate_action', new_callable=AsyncMock)
    @patch('bot_helper.take_action', new_callable=AsyncMock)
    async def test_on_message_no_action(self, mock_take_action, mock_get_appropriate_action, mock_get_model):
        """
        Test that the on_message event does not trigger a moderation action when the AI returns a null action.
        """
        from cogs.events import EventsCog

        # Mock the AI model to return a null action
        mock_get_appropriate_action.return_value = (ActionType.NULL, "No action needed")

        # Create a mock bot and cog
        mock_bot = MagicMock()
        cog = EventsCog(mock_bot)

        # Create a mock message
        message = MagicMock(spec=discord.Message)
        message.author.bot = False
        message.author.guild_permissions.administrator = False
        message.clean_content = "This is a normal message."
        message.guild.id = 123
        message.channel.id = 456
        message.author.name = "testuser"

        # Call the on_message event handler
        await cog.on_message(message)

        # Assert that the AI action was called but no moderation action was taken
        mock_get_appropriate_action.assert_called_once()
        mock_take_action.assert_not_called()

@patch('ai_model.get_model', return_value=(MagicMock(), MagicMock(), "System Prompt Template: {SERVER_RULES}"))
class TestCogs(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        """Set up test fixtures."""
        self.mock_bot = MagicMock()
        self.mock_bot.latency = 0.05  # 50ms latency

    async def test_util_cog_test_command(self, mock_get_model):
        """Test the util cog test command."""
        from cogs.util import UtilCog

        cog = UtilCog(self.mock_bot)

        # Create mock context
        ctx = MagicMock(spec=discord.ApplicationContext)
        ctx.respond = AsyncMock()

        # Test the command directly by calling the actual callback
        await cog.test.callback(cog, ctx) # type: ignore

        # Verify response
        ctx.respond.assert_called_once()
        call_args = ctx.respond.call_args[0][0]
        self.assertIn("online and working", call_args)
        self.assertIn("50.00 ms", call_args)

    async def test_moderation_cog_permission_checks(self, mock_get_model):
        """Test moderation cog permission checking."""
        from cogs.moderation import ModerationCog

        with patch('bot_helper.has_permissions') as mock_has_perms:
            mock_has_perms.return_value = False

            cog = ModerationCog(self.mock_bot)

            # Create mock context and user
            ctx = MagicMock(spec=discord.ApplicationContext)
            ctx.respond = AsyncMock()
            user = MagicMock(spec=discord.Member)

            # Test permission check failure
            result = await cog._check_moderation_permissions(ctx, user, 'manage_messages')

            self.assertFalse(result)
            ctx.respond.assert_called_once()

    def test_cog_loading(self, mock_get_model):
        """Test that all cogs can be imported successfully."""
        try:
            from cogs.util import UtilCog
            from cogs.moderation import ModerationCog
            from cogs.debug import DebugCog
            from cogs.events import EventsCog
            self.assertTrue(True)  # If we get here, imports succeeded
        except ImportError as e:
            self.fail(f"Failed to import cogs: {e}")

class TestBotConfig(unittest.TestCase):
    def test_bot_config(self):
        """Test the bot configuration module."""
        from bot_config import BotConfig

        config = BotConfig()

        # Test server rules
        config.set_server_rules(123, "Test rules")
        rules = config.get_server_rules(123)
        self.assertEqual(rules, "Test rules")

        # Test chat history
        message_data = {"role": "user", "content": "Hello", "username": "testuser"}
        config.add_message_to_history(456, message_data)
        history = config.get_chat_history(456)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0], message_data)

if __name__ == "__main__":
    unittest.main()
