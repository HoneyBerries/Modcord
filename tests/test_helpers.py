"""
Tests for the helper functions.
"""

import unittest
from unittest.mock import MagicMock, AsyncMock
import discord

from src.bot.utils import helpers

class TestHelpers(unittest.IsolatedAsyncioTestCase):
    """
    Tests for the helper functions.
    """
    def test_parse_duration_to_seconds(self):
        """
        Tests the parse_duration_to_seconds function.
        """
        self.assertEqual(helpers.parse_duration_to_seconds("60 secs"), 60)
        self.assertEqual(helpers.parse_duration_to_seconds("5 mins"), 300)
        self.assertEqual(helpers.parse_duration_to_seconds("1 hour"), 3600)
        self.assertEqual(helpers.parse_duration_to_seconds("1 day"), 86400)
        self.assertEqual(helpers.parse_duration_to_seconds("1 week"), 604800)
        self.assertEqual(helpers.parse_duration_to_seconds("Till the end of time"), 0)
        self.assertEqual(helpers.parse_duration_to_seconds("invalid duration"), 0)

    def test_has_permissions(self):
        """
        Tests the has_permissions function.
        """
        mock_ctx = MagicMock(spec=discord.ApplicationContext)
        mock_member = MagicMock(spec=discord.Member)

        mock_member.guild_permissions.ban_members = True
        mock_member.guild_permissions.kick_members = True
        mock_ctx.author = mock_member
        self.assertTrue(helpers.has_permissions(mock_ctx, ban_members=True, kick_members=True))

        mock_member.guild_permissions.ban_members = False
        self.assertFalse(helpers.has_permissions(mock_ctx, ban_members=True))

        mock_ctx.author = MagicMock(spec=discord.User)
        self.assertFalse(helpers.has_permissions(mock_ctx, ban_members=True))

    async def test_send_dm_to_user(self):
        """
        Tests the send_dm_to_user function.
        """
        mock_user = MagicMock(spec=discord.Member)
        mock_user.send = AsyncMock()

        result = await helpers.send_dm_to_user(mock_user, "test message")
        self.assertTrue(result)
        mock_user.send.assert_called_once_with("test message")

        mock_user.send.reset_mock()
        mock_user.send.side_effect = discord.Forbidden(MagicMock(), "DM disabled")
        result = await helpers.send_dm_to_user(mock_user, "test message")
        self.assertFalse(result)
        mock_user.send.assert_called_once_with("test message")

if __name__ == "__main__":
    unittest.main()
