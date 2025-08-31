import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from actions import ActionType
import discord

class TestRefactoredBot(unittest.IsolatedAsyncioTestCase):
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_bot = MagicMock()
        self.mock_bot.latency = 0.05  # 50ms latency
        
    async def test_general_cog_test_command(self):
        """Test the general cog test command."""
        from cogs.general import GeneralCog
        
        cog = GeneralCog(self.mock_bot)
        
        # Create mock context
        ctx = MagicMock(spec=discord.ApplicationContext)
        ctx.respond = AsyncMock()
        
        # Test the command directly
        await cog.test.callback(cog, ctx)
        
        # Verify response
        ctx.respond.assert_called_once()
        call_args = ctx.respond.call_args[0][0]
        self.assertIn("online and working", call_args)
        self.assertIn("50.00 ms", call_args)
    
    async def test_bot_config(self):
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
    
    async def test_moderation_cog_permission_checks(self):
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
    
    def test_cog_loading(self):
        """Test that all cogs can be imported successfully."""
        try:
            from cogs.general import GeneralCog
            from cogs.moderation import ModerationCog
            from cogs.debug import DebugCog
            # Skip events cog as it imports AI model
            self.assertTrue(True)  # If we get here, imports succeeded
        except ImportError as e:
            self.fail(f"Failed to import cogs: {e}")

if __name__ == "__main__":
    unittest.main()