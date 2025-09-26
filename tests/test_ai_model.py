import unittest
import json
from unittest.mock import MagicMock, patch, AsyncMock
from modcord.util.actions import ActionType

@patch(
    'modcord.ai_model.moderation_processor.get_model',
    new_callable=AsyncMock,
    return_value=(MagicMock(), MagicMock(), "System Prompt Template: {SERVER_RULES}")
)
class TestAIModel(unittest.IsolatedAsyncioTestCase):
    async def test_parse_action(self, mock_get_model):
        from modcord.ai.ai_model import moderation_processor
        # Test ban action (JSON input)
        action, reason = await moderation_processor.parse_action(json.dumps({"action": "ban", "reason": "User was spamming"}))
        self.assertEqual(action, ActionType.BAN)
        self.assertEqual(reason, "User was spamming")

        # Test warn action (JSON input)
        action, reason = await moderation_processor.parse_action(json.dumps({"action": "warn", "reason": "User was being rude"}))
        self.assertEqual(action, ActionType.WARN)
        self.assertEqual(reason, "User was being rude")

        # Test null action (JSON input)
        action, reason = await moderation_processor.parse_action(json.dumps({"action": "null", "reason": "No action needed"}))
        self.assertEqual(action, ActionType.NULL)
        self.assertEqual(reason, "No action needed")

        # Test invalid action (JSON input) -> expect unknown action type
        action, reason = await moderation_processor.parse_action(json.dumps({"action": "invalid", "reason": "This is not a valid action"}))
        self.assertEqual(action, ActionType.NULL)
        self.assertEqual(reason, "unknown action type")

    @patch('modcord.ai_model.moderation_processor.submit_inference', new_callable=AsyncMock)
    async def test_get_appropriate_action(self, mock_submit_inference, mock_get_model):
        """
        Unit test for get_appropriate_action. Mocks the inference call.
        """
        from modcord.ai.ai_model import moderation_processor

        # Mock the AI's response (JSON)
        mock_submit_inference.return_value = json.dumps({"action": "kick", "reason": "User was being disruptive."})

        action, reason = await moderation_processor.get_appropriate_action(
            history=[],
            user_id=12345,
            current_message="some disruptive message",
            server_rules="Be nice."
        )

        # Verify that the correct action was parsed
        self.assertEqual(action, ActionType.KICK)
        self.assertEqual(reason, "User was being disruptive.")

        # Verify that submit_inference was called
        mock_submit_inference.assert_called_once()

if __name__ == "__main__":
    unittest.main()