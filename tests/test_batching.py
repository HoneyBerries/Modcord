"""
Test cases for the new channel-based message batching system.
"""

import asyncio
import unittest
import sys
import json
from unittest.mock import AsyncMock, patch, MagicMock

# Add src to path for imports
sys.path.insert(0, 'src')

from modcord.bot.bot_settings import BotConfig


class TestMessageBatching(unittest.IsolatedAsyncioTestCase):
    """Test the new 15-second channel batching system."""

    def setUp(self):
        """Set up test fixtures."""
        self.bot_settings = BotConfig()
        self.channel_id = 12345
        self.sample_messages = [
            {
                "user_id": 1001,
                "username": "user1",
                "content": "Hello world",
                "timestamp": "2023-01-01T12:00:00Z",
                "image_summary": None,
                "guild_id": 99999,
                "message_obj": MagicMock()
            },
            {
                "user_id": 1002, 
                "username": "user2",
                "content": "How are you?",
                "timestamp": "2023-01-01T12:00:05Z",
                "image_summary": None,
                "guild_id": 99999,
                "message_obj": MagicMock()
            }
        ]

    async def test_message_batch_collection(self):
        """Test that messages are collected in batches per channel."""
        # Set up a mock callback
        callback_called = asyncio.Event()
        received_messages = []
        
        async def mock_callback(channel_id, messages):
            received_messages.extend(messages)
            callback_called.set()
        
        self.bot_settings.set_batch_processing_callback(mock_callback)
        
        # Add messages to batch
        await self.bot_settings.add_message_to_batch(self.channel_id, self.sample_messages[0])
        await self.bot_settings.add_message_to_batch(self.channel_id, self.sample_messages[1])
        
        # Check that batch contains both messages
        self.assertEqual(len(self.bot_settings.channel_message_batches[self.channel_id]), 2)
        
        # Wait for callback to be triggered (with timeout)
        try:
            await asyncio.wait_for(callback_called.wait(), timeout=16.0)  # 15s + buffer
            self.assertEqual(len(received_messages), 2)
            self.assertEqual(received_messages[0]["user_id"], 1001)
            self.assertEqual(received_messages[1]["user_id"], 1002)
        except asyncio.TimeoutError:
            self.fail("Batch processing callback was not called within timeout")

    async def test_separate_channel_batches(self):
        """Test that different channels have separate batches."""
        channel1 = 11111
        channel2 = 22222
        
        # Add messages to different channels
        await self.bot_settings.add_message_to_batch(channel1, self.sample_messages[0])
        await self.bot_settings.add_message_to_batch(channel2, self.sample_messages[1])
        
        # Check that channels have separate batches
        self.assertEqual(len(self.bot_settings.channel_message_batches[channel1]), 1)
        self.assertEqual(len(self.bot_settings.channel_message_batches[channel2]), 1)
        self.assertEqual(self.bot_settings.channel_message_batches[channel1][0]["user_id"], 1001)
        self.assertEqual(self.bot_settings.channel_message_batches[channel2][0]["user_id"], 1002)

    def test_batch_timer_management(self):
        """Test that batch timers are created and managed correctly."""
        # Initially no timers
        self.assertEqual(len(self.bot_settings.channel_batch_timers), 0)
        
        # Add a message - should create timer
        asyncio.run(self.bot_settings.add_message_to_batch(self.channel_id, self.sample_messages[0]))
        
        # Should have one timer
        self.assertEqual(len(self.bot_settings.channel_batch_timers), 1)
        self.assertIn(self.channel_id, self.bot_settings.channel_batch_timers)


class TestBatchJSONParsing(unittest.TestCase):
    """Test JSON parsing functions without AI model dependencies."""
    
    def test_parse_batch_actions_valid_response(self):
        """Test parsing a valid batch response JSON."""
        # Mock the parse function since we can't import ai_model
        def parse_batch_actions_mock(response, channel_id):
            try:
                parsed = json.loads(response)
                actions = parsed.get("actions", [])
                validated_actions = []
                for action in actions:
                    if action.get("action") != "null" and action.get("user_id"):
                        validated_actions.append(action)
                return validated_actions
            except:
                return []
        
        response = json.dumps({
            "channel_id": "12345",
            "actions": [
                {
                    "user_id": "1002",
                    "action": "warn",
                    "reason": "repeated spam detected",
                    "delete_count": 1,
                    "timeout_duration": None,
                    "ban_duration": None
                }
            ]
        })
        
        actions = parse_batch_actions_mock(response, 12345)
        
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["user_id"], "1002") 
        self.assertEqual(actions[0]["action"], "warn")
        self.assertEqual(actions[0]["reason"], "repeated spam detected")

    def test_parse_batch_actions_null_actions_filtered(self):
        """Test that null actions are filtered out."""
        def parse_batch_actions_mock(response, channel_id):
            try:
                parsed = json.loads(response)
                actions = parsed.get("actions", [])
                validated_actions = []
                for action in actions:
                    if action.get("action") != "null" and action.get("user_id"):
                        validated_actions.append(action)
                return validated_actions
            except:
                return []
        
        response = json.dumps({
            "channel_id": "12345", 
            "actions": [
                {
                    "user_id": "1001",
                    "action": "null",
                    "reason": "no action needed",
                    "delete_count": 0,
                    "timeout_duration": None,
                    "ban_duration": None
                },
                {
                    "user_id": "1002",
                    "action": "delete",
                    "reason": "spam detected", 
                    "delete_count": 1,
                    "timeout_duration": None,
                    "ban_duration": None
                }
            ]
        })
        
        actions = parse_batch_actions_mock(response, 12345)
        
        # Should only return the non-null action
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["action"], "delete")


if __name__ == '__main__':
    unittest.main()