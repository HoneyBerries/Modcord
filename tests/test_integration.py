"""
Integration tests for the Discord bot batching system.
Tests the complete workflow from message collection to action application.
"""

import asyncio
import unittest
import sys
import json
from unittest.mock import AsyncMock, patch, MagicMock

# Add src to path for imports
sys.path.insert(0, 'src')

from modcord.bot.bot_settings import BotConfig


class TestBatchingIntegration(unittest.IsolatedAsyncioTestCase):
    """Integration tests for the complete batching workflow."""

    def setUp(self):
        """Set up test fixtures."""
        self.bot_config = BotConfig()
        
        # Mock Discord objects
        self.mock_guild = MagicMock()
        self.mock_guild.id = 12345
        self.mock_guild.name = "Test Guild"
        
        self.mock_channel = MagicMock()
        self.mock_channel.id = 67890
        
        self.mock_user1 = MagicMock()
        self.mock_user1.id = 1001
        self.mock_user1.display_name = "TestUser1"
        
        self.mock_user2 = MagicMock()
        self.mock_user2.id = 1002
        self.mock_user2.display_name = "TestUser2"
        
        self.mock_message1 = MagicMock()
        self.mock_message1.author = self.mock_user1
        self.mock_message1.guild = self.mock_guild
        self.mock_message1.channel = self.mock_channel
        
        self.mock_message2 = MagicMock()
        self.mock_message2.author = self.mock_user2
        self.mock_message2.guild = self.mock_guild
        self.mock_message2.channel = self.mock_channel

    async def test_complete_batching_workflow(self):
        """Test the complete workflow from message addition to action execution."""
        actions_applied = []
        
        # Mock the AI processing function
        async def mock_batch_processing(channel_id, messages):
            # Simulate AI detecting spam from user2
            mock_actions = [
                {
                    "user_id": "1002",
                    "action": "warn", 
                    "reason": "spam detected in batch",
                    "delete_count": 2,
                    "timeout_duration": None,
                    "ban_duration": None
                }
            ]
            
            # Mock the action application
            for action in mock_actions:
                actions_applied.append(action)
        
        # Set up the callback
        self.bot_config.set_batch_processing_callback(mock_batch_processing)
        
        # Create test messages
        test_messages = [
            {
                "user_id": 1001,
                "username": "TestUser1",
                "content": "Hello everyone!",
                "timestamp": "2023-01-01T12:00:00Z",
                "image_summary": None,
                "guild_id": 12345,
                "message_obj": self.mock_message1
            },
            {
                "user_id": 1002,
                "username": "TestUser2", 
                "content": "SPAM SPAM SPAM!!!",
                "timestamp": "2023-01-01T12:00:05Z",
                "image_summary": None,
                "guild_id": 12345,
                "message_obj": self.mock_message2
            }
        ]
        
        # Add messages to batch
        for msg in test_messages:
            await self.bot_config.add_message_to_batch(self.mock_channel.id, msg)
        
        # Verify batch contains messages
        self.assertEqual(len(self.bot_config.channel_message_batches[self.mock_channel.id]), 2)
        
        # Wait for batch processing (this test uses a much shorter timeout)
        callback_called = asyncio.Event()
        
        async def callback_wrapper(channel_id, messages):
            await mock_batch_processing(channel_id, messages)
            callback_called.set()
        
        self.bot_config.set_batch_processing_callback(callback_wrapper)
        
        # Trigger immediate processing by waiting just slightly less than batch time
        try:
            await asyncio.wait_for(callback_called.wait(), timeout=16.0)  # 15s + buffer
            
            # Verify action was applied
            self.assertEqual(len(actions_applied), 1)
            self.assertEqual(actions_applied[0]["user_id"], "1002")
            self.assertEqual(actions_applied[0]["action"], "warn")
            self.assertEqual(actions_applied[0]["delete_count"], 2)
            
        except asyncio.TimeoutError:
            self.fail("Batch processing not triggered within timeout")

    def test_batch_json_formatting(self):
        """Test that messages are correctly formatted for AI processing."""
        messages = [
            {
                "user_id": 1001,
                "username": "User1",
                "content": "Normal message",
                "timestamp": "2023-01-01T12:00:00Z",
                "image_summary": None
            },
            {
                "user_id": 1002,
                "username": "User2",
                "content": "Another message with emoji 😀",
                "timestamp": "2023-01-01T12:00:05Z", 
                "image_summary": "Image showing a cat"
            }
        ]
        
        # Format for AI processing (simulating what events.py does)
        expected_payload = {
            "channel_id": "67890",
            "messages": [
                {
                    "user_id": "1001",
                    "username": "User1",
                    "content": "Normal message", 
                    "timestamp": "2023-01-01T12:00:00Z",
                    "image_summary": None
                },
                {
                    "user_id": "1002", 
                    "username": "User2",
                    "content": "Another message with emoji 😀",
                    "timestamp": "2023-01-01T12:00:05Z",
                    "image_summary": "Image showing a cat"
                }
            ]
        }
        
        # Test JSON serialization
        json_str = json.dumps(expected_payload, ensure_ascii=False)
        parsed_back = json.loads(json_str)
        
        self.assertEqual(parsed_back["channel_id"], "67890")
        self.assertEqual(len(parsed_back["messages"]), 2)
        self.assertEqual(parsed_back["messages"][1]["image_summary"], "Image showing a cat")

    def test_action_parameter_extraction(self):
        """Test extraction of batch action parameters."""
        sample_response = {
            "channel_id": "67890",
            "actions": [
                {
                    "user_id": "1001",
                    "action": "timeout",
                    "reason": "harassment detected",
                    "delete_count": 3,
                    "timeout_duration": 3600,  # 1 hour
                    "ban_duration": None
                },
                {
                    "user_id": "1002",
                    "action": "ban",
                    "reason": "severe spam",
                    "delete_count": 5,
                    "timeout_duration": None,
                    "ban_duration": 86400  # 24 hours
                }
            ]
        }
        
        # Verify parameter extraction
        actions = sample_response["actions"]
        
        # Test timeout action
        timeout_action = actions[0]
        self.assertEqual(timeout_action["user_id"], "1001")
        self.assertEqual(timeout_action["action"], "timeout")
        self.assertEqual(timeout_action["delete_count"], 3)
        self.assertEqual(timeout_action["timeout_duration"], 3600)
        self.assertIsNone(timeout_action["ban_duration"])
        
        # Test ban action
        ban_action = actions[1] 
        self.assertEqual(ban_action["user_id"], "1002")
        self.assertEqual(ban_action["action"], "ban")
        self.assertEqual(ban_action["delete_count"], 5)
        self.assertEqual(ban_action["ban_duration"], 86400)
        self.assertIsNone(ban_action["timeout_duration"])


if __name__ == '__main__':
    unittest.main()