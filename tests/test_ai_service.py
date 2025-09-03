"""
Tests for the AI service.
"""

import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio

from src.bot.models.action import ActionType
from src.bot.utils.helpers import parse_action

class TestParseAction(unittest.TestCase):
    """
    Tests for the parse_action function.
    """
    def test_valid_actions(self):
        """
        Tests that valid actions are parsed correctly.
        """
        test_cases = {
            "ban: User was spamming": (ActionType.BAN, "User was spamming"),
            "warn: User was being rude": (ActionType.WARN, "User was being rude"),
            "null: No action needed": (ActionType.NULL, "no action needed"),
            "kick: Disruptive behavior": (ActionType.KICK, "Disruptive behavior"),
            "timeout: User is flooding chat": (ActionType.TIMEOUT, "User is flooding chat"),
            "delete: Inappropriate content": (ActionType.DELETE, "Inappropriate content"),
        }
        for response, expected in test_cases.items():
            with self.subTest(response=response):
                action, reason = parse_action(response)
                self.assertEqual(action, expected[0])
                self.assertEqual(reason, expected[1])

    def test_invalid_actions(self):
        """
        Tests that invalid actions are handled correctly.
        """
        test_cases = {
            "invalid: This is not a valid action": (ActionType.NULL, "invalid AI response format"),
            "ban User was spamming": (ActionType.NULL, "invalid AI response format"),
            "warn:User was being rude": (ActionType.WARN, "User was being rude"),
        }
        for response, expected in test_cases.items():
            with self.subTest(response=response):
                action, reason = parse_action(response)
                self.assertEqual(action, expected[0])
                self.assertEqual(reason, expected[1])

@patch('src.bot.services.ai_service.AIService._load_model')
class TestAIService(unittest.IsolatedAsyncioTestCase):
    """
    Tests for the AIService class.
    """

    def setUp(self):
        """
        Set up the test case.
        """
        from src.bot.services.ai_service import AIService
        self.ai_service = AIService()

    @patch('src.bot.services.ai_service.AIService.submit_inference', new_callable=AsyncMock)
    async def test_get_appropriate_action(self, mock_submit_inference, mock_load_model):
        """
        Tests the get_appropriate_action method.
        """
        mock_submit_inference.return_value = "kick: User was being disruptive."

        action, reason = await self.ai_service.get_appropriate_action(
            current_message="some disruptive message",
            history=[],
            username="testuser",
            server_rules="Be nice."
        )

        self.assertEqual(action, ActionType.KICK)
        self.assertEqual(reason, "User was being disruptive.")
        mock_submit_inference.assert_called_once()

if __name__ == "__main__":
    unittest.main()
