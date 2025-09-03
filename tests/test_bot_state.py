"""
Tests for the bot state.
"""

import unittest

from src.bot.bot_state import BotState

class TestBotState(unittest.TestCase):
    """
    Tests for the BotState class.
    """
    def test_bot_state(self):
        """
        Tests the BotState class.
        """
        bot_state = BotState()

        # Test server rules
        bot_state.set_server_rules(123, "Test rules")
        rules = bot_state.get_server_rules(123)
        self.assertEqual(rules, "Test rules")

        # Test chat history
        message_data = {"role": "user", "content": "Hello", "username": "testuser"}
        bot_state.add_message_to_history(456, message_data)
        history = bot_state.get_chat_history(456)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0], message_data)

if __name__ == "__main__":
    unittest.main()
