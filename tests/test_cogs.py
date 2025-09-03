"""
Tests for the cogs.
"""

import unittest
from unittest.mock import MagicMock, AsyncMock, patch

import discord

from src.bot.models.action import ActionType

class TestEventsCog(unittest.IsolatedAsyncioTestCase):
    """
    Tests for the EventsCog.
    """
    @patch('src.bot.cogs.events.get_ai_service')
    @patch('src.bot.cogs.events.ModerationService')
    async def test_on_message_moderation_action(self, mock_moderation_service, mock_get_ai_service):
        """
        Tests that on_message triggers a moderation action when the AI returns a non-null action.
        """
        from src.bot.cogs.events import EventsCog

        mock_ai_service = MagicMock()
        mock_ai_service.get_appropriate_action = AsyncMock(return_value=(ActionType.BAN, "User was spamming"))
        mock_get_ai_service.return_value = mock_ai_service

        mock_bot = MagicMock()
        cog = EventsCog(mock_bot)

        message = MagicMock(spec=discord.Message)
        message.author.bot = False
        message.author.guild_permissions.administrator = False
        message.clean_content = "This is a test message that should trigger a ban."
        message.guild.id = 123
        message.channel.id = 456
        message.author.name = "testuser"

        await cog.on_message(message)

        mock_ai_service.get_appropriate_action.assert_called_once()
        cog.moderation_service.take_action.assert_called_once_with(ActionType.BAN, "User was spamming", message)

    @patch('src.bot.cogs.events.get_ai_service')
    @patch('src.bot.cogs.events.ModerationService')
    async def test_on_message_no_action(self, mock_moderation_service, mock_get_ai_service):
        """
        Tests that on_message does not trigger a moderation action when the AI returns a null action.
        """
        from src.bot.cogs.events import EventsCog

        mock_get_appropriate_action.return_value = (ActionType.NULL, "No action needed")

        mock_bot = MagicMock()
        cog = EventsCog(mock_bot)

        message = MagicMock(spec=discord.Message)
        message.author.bot = False
        message.author.guild_permissions.administrator = False
        message.clean_content = "This is a normal message."
        message.guild.id = 123
        message.channel.id = 456
        message.author.name = "testuser"

        await cog.on_message(message)

        mock_get_appropriate_action.assert_called_once()
        mock_take_action.assert_not_called()


class TestGeneralCog(unittest.IsolatedAsyncioTestCase):
    """
    Tests for the GeneralCog.
    """
    def setUp(self):
        self.mock_bot = MagicMock()
        self.mock_bot.latency = 0.05

    async def test_test_command(self):
        """
        Tests the test command.
        """
        from src.bot.cogs.general import GeneralCog

        cog = GeneralCog(self.mock_bot)
        ctx = MagicMock(spec=discord.ApplicationContext)
        ctx.respond = AsyncMock()

        await cog.test.callback(cog, ctx)

        ctx.respond.assert_called_once()
        call_args = ctx.respond.call_args[0][0]
        self.assertIn("online and working", call_args)
        self.assertIn("50.00 ms", call_args)

class TestModerationCog(unittest.IsolatedAsyncioTestCase):
    """
    Tests for the ModerationCog.
    """
    def setUp(self):
        self.mock_bot = MagicMock()

    @patch('src.bot.utils.helpers.has_permissions', return_value=False)
    async def test_permission_checks(self, mock_has_perms):
        """
        Tests the permission checking in the moderation cog.
        """
        from src.bot.cogs.moderation import ModerationCog

        cog = ModerationCog(self.mock_bot)

        ctx = MagicMock(spec=discord.ApplicationContext)
        ctx.respond = AsyncMock()
        user = MagicMock(spec=discord.Member)

        result = await cog._check_moderation_permissions(ctx, user, 'manage_messages')

        self.assertFalse(result)
        ctx.respond.assert_called_once()

if __name__ == "__main__":
    unittest.main()
