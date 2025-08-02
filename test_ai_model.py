import unittest
import asyncio
from unittest.mock import MagicMock, patch
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

    def test_ai_model_response_system(self):
        """
        Integration test for the AI model's actual response system.
        Tests the full pipeline from message input to moderation action.
        """
        from ai_model import get_appropriate_action, start_batch_worker
        
        async def run_ai_test():
            # Start the batch worker for processing
            start_batch_worker()
            
            # Test case 1: Spam message should trigger action
            spam_message = "BUY CHEAP CRYPTO NOW!!! CLICK HERE!!! AMAZING DEALS!!!\nBUY CHEAP CRYPTO NOW!!! CLICK HERE!!! AMAZING DEALS!!!\nBUY CHEAP CRYPTO NOW!!! CLICK HERE!!! AMAZING DEALS!!!"
            history = [
                {"role": "user", "content": "Hello everyone", "username": "user1"},
                {"role": "user", "content": "How is everyone doing?", "username": "user2"}
            ]
            server_rules = "No spam, no advertising, be respectful"
            
            action, reason = await get_appropriate_action(
                current_message=spam_message,
                history=history,
                username="spammer123",
                server_rules=server_rules
            )
            
            # The AI should detect this as problematic (not NULL)
            self.assertNotEqual(action, ActionType.NULL)
            self.assertIsInstance(reason, str)
            self.assertGreater(len(reason), 0)
            print(f"Spam test - Action: {action}, Reason: {reason}")
            
            # Test case 2: Normal message should be NULL
            normal_message = "Thanks for the help everyone!"
            action2, reason2 = await get_appropriate_action(
                current_message=normal_message,
                history=history,
                username="normaluser",
                server_rules=server_rules
            )
            
            # Should be no action for normal message
            self.assertEqual(action2, ActionType.NULL)
            print(f"Normal test - Action: {action2}, Reason: {reason2}")
            
            # Test case 3: Toxic message should trigger action
            toxic_message = "You're all idiots and this server sucks"
            action3, reason3 = await get_appropriate_action(
                current_message=toxic_message,
                history=history,
                username="toxicuser",
                server_rules=server_rules
            )
            
            # Should trigger some moderation action
            self.assertNotEqual(action3, ActionType.NULL)
            print(f"Toxic test - Action: {action3}, Reason: {reason3}")
            
        # Run the async test
        asyncio.run(run_ai_test())

if __name__ == "__main__":
    # We need to mock the model loading here to prevent the model from being loaded when the test is run
    import ai_model
    
    # Only mock if running parse_action tests, not the full AI test
    import sys
    if len(sys.argv) > 1 and 'test_parse_action' in sys.argv[1]:
        ai_model.model, ai_model.tokenizer, ai_model.BASE_SYSTEM_PROMPT = ai_model.init_ai_model(MagicMock(), MagicMock())
    
    unittest.main()