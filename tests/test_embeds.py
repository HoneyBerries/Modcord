"""
Tests for the embed generation functions.
"""

import unittest
from unittest.mock import MagicMock
import discord

from src.bot.models.action import ActionType
from src.bot.utils.embeds import create_punishment_embed

class TestEmbeds(unittest.IsolatedAsyncioTestCase):
    """
    Tests for the embed generation functions.
    """
    async def test_create_punishment_embed(self):
        """
        Tests the create_punishment_embed function.
        """
        mock_user = MagicMock(spec=discord.User)
        mock_user.mention = "@testuser"
        mock_user.id = 12345
        mock_issuer = MagicMock(spec=discord.User)
        mock_issuer.mention = "@moderator"
        mock_bot_user = MagicMock(spec=discord.ClientUser)
        mock_bot_user.name = "TestBot"

        embed = await create_punishment_embed(
            action_type=ActionType.BAN,
            user=mock_user,
            reason="Test reason",
            duration_str="1 hour",
            issuer=mock_issuer,
            bot_user=mock_bot_user
        )

        self.assertEqual(embed.title, "🔨 Ban Issued")
        self.assertEqual(embed.color, discord.Color.red())
        self.assertEqual(len(embed.fields), 5)
        self.assertEqual(embed.fields[0].name, "User")
        self.assertEqual(embed.fields[0].value, "@testuser (`12345`)")
        self.assertEqual(embed.fields[2].name, "Moderator")
        self.assertEqual(embed.fields[2].value, "@moderator")
        self.assertEqual(embed.fields[4].name, "Duration")
        self.assertIn("1 hour", embed.fields[4].value)

if __name__ == "__main__":
    unittest.main()
