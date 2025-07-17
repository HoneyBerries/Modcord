import unittest
from unittest.mock import MagicMock
from actions import ActionType

class TestAIModel(unittest.TestCase):
    def test_parse_action(self):
        # We don't need to mock the model loading here since we are only testing the parse_action function
        from ai_model import parse_action
        # Test ban action
        action, reason = parse_action("ban: User was spamming")
        self.assertEqual(action, ActionType.BAN)
        self.assertEqual(reason, "User was spamming")

        # Test warn action
        action, reason = parse_action("warn: User was being rude")
        self.assertEqual(action, ActionType.WARN)
        self.assertEqual(reason, "User was being rude")

        # Test null action
        action, reason = parse_action("null: No action needed")
        self.assertEqual(action, ActionType.NULL)
        self.assertEqual(reason, "no action needed")

        # Test invalid action
        action, reason = parse_action("invalid: This is not a valid action")
        self.assertEqual(action, ActionType.NULL)
        self.assertEqual(reason, "invalid AI response format")

if __name__ == "__main__":
    # We need to mock the model loading here to prevent the model from being loaded when the test is run
    import ai_model
    ai_model.model, ai_model.tokenizer, ai_model.BASE_SYSTEM_PROMPT = ai_model.init_ai_model(MagicMock(), MagicMock())
    unittest.main()
