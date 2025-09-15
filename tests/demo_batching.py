#!/usr/bin/env python3
"""
Demo script for the new Discord bot batching system.
Shows how messages are batched per channel every 15 seconds.
"""

import asyncio
import json
from unittest.mock import MagicMock
from modcord.bot_config import BotConfig


async def demo_batch_processing():
    """Demonstrate the channel-based batching system."""
    print("🤖 Discord Bot Batching System Demo")
    print("=" * 50)
    
    # Initialize the bot config
    bot_config = BotConfig()
    
    # Track processed batches
    processed_batches = []
    
    async def mock_ai_processor(channel_id: int, messages: list[dict]):
        """Mock AI processor that simulates batch processing."""
        print(f"\n🧠 AI Processing batch for channel {channel_id}")
        print(f"   📝 Processing {len(messages)} messages")
        
        # Simulate AI analysis
        actions = []
        for msg in messages:
            content = msg["content"].lower()
            if "spam" in content or content.count("!") > 3:
                actions.append({
                    "user_id": str(msg["user_id"]),
                    "action": "warn",
                    "reason": f"Spam detected: '{msg['content'][:30]}...'",
                    "delete_count": 1,
                    "timeout_duration": None,
                    "ban_duration": None
                })
        
        if actions:
            print(f"   ⚡ Generated {len(actions)} moderation actions")
            for action in actions:
                print(f"      - {action['action']} user {action['user_id']}: {action['reason']}")
        else:
            print("   ✅ No moderation actions needed")
        
        processed_batches.append({
            "channel_id": channel_id,
            "message_count": len(messages),
            "actions": actions
        })
    
    # Set up the AI processor
    bot_config.set_batch_processing_callback(mock_ai_processor)
    
    # Simulate messages in different channels
    channel_1 = 111111
    channel_2 = 222222
    
    print(f"\n📨 Simulating messages in channel {channel_1}")
    
    # Add some normal messages
    await bot_config.add_message_to_batch(channel_1, {
        "user_id": 1001,
        "username": "Alice",
        "content": "Hey everyone, how's it going?",
        "timestamp": "2023-01-01T12:00:00Z",
        "image_summary": None,
        "guild_id": 99999,
        "message_obj": MagicMock()
    })
    print("   • Alice: Hey everyone, how's it going?")
    
    await bot_config.add_message_to_batch(channel_1, {
        "user_id": 1002,
        "username": "Bob",
        "content": "I'm doing great! Working on a new project.",
        "timestamp": "2023-01-01T12:00:05Z",
        "image_summary": None,
        "guild_id": 99999,
        "message_obj": MagicMock()
    })
    print("   • Bob: I'm doing great! Working on a new project.")
    
    # Add a spam message
    await bot_config.add_message_to_batch(channel_1, {
        "user_id": 1003,
        "username": "Spammer",
        "content": "BUY NOW!!!! AMAZING DEALS!!!! CLICK HERE NOW!!!!",
        "timestamp": "2023-01-01T12:00:10Z",
        "image_summary": None,
        "guild_id": 99999,
        "message_obj": MagicMock()
    })
    print("   • Spammer: BUY NOW!!!! AMAZING DEALS!!!! CLICK HERE NOW!!!!")
    
    # Add messages to a different channel
    print(f"\n📨 Simulating messages in channel {channel_2}")
    
    await bot_config.add_message_to_batch(channel_2, {
        "user_id": 2001,
        "username": "Charlie",
        "content": "This is spam spam spam everywhere!",
        "timestamp": "2023-01-01T12:00:02Z",
        "image_summary": None,
        "guild_id": 99999,
        "message_obj": MagicMock()
    })
    print("   • Charlie: This is spam spam spam everywhere!")
    
    print(f"\n⏳ Waiting for 15-second batch processing...")
    print("   (In a real bot, this would happen automatically)")
    
    # Wait for batches to be processed (15 seconds + buffer)
    try:
        await asyncio.wait_for(
            asyncio.gather(*[
                asyncio.sleep(16),  # Wait for batch processing
            ]),
            timeout=20
        )
    except asyncio.TimeoutError:
        print("⚠️  Batch processing timeout (this is expected in demo)")
    
    # Show results
    print(f"\n📊 Batch Processing Summary")
    print("=" * 30)
    
    if processed_batches:
        for batch in processed_batches:
            print(f"Channel {batch['channel_id']}: {batch['message_count']} messages, {len(batch['actions'])} actions")
    else:
        print("No batches processed yet (timers still running)")
    
    # Show the JSON format that would be sent to AI
    print(f"\n🔍 Example JSON payload for AI model:")
    sample_payload = {
        "channel_id": str(channel_1),
        "messages": [
            {
                "user_id": "1001",
                "username": "Alice",
                "timestamp": "2023-01-01T12:00:00Z",
                "content": "Hey everyone, how's it going?",
                "image_summary": None
            },
            {
                "user_id": "1003",
                "username": "Spammer", 
                "timestamp": "2023-01-01T12:00:10Z",
                "content": "BUY NOW!!!! AMAZING DEALS!!!! CLICK HERE NOW!!!!",
                "image_summary": None
            }
        ]
    }
    
    print(json.dumps(sample_payload, indent=2))
    
    # Show expected AI response format
    print(f"\n🤖 Example AI response format:")
    sample_response = {
        "channel_id": str(channel_1),
        "actions": [
            {
                "user_id": "1003",
                "action": "warn",
                "reason": "Excessive spam and advertising",
                "delete_count": 1,
                "timeout_duration": None,
                "ban_duration": None
            }
        ]
    }
    
    print(json.dumps(sample_response, indent=2))
    
    print(f"\n✅ Demo completed!")
    print(f"📈 Efficiency gained: Instead of 4 individual AI calls, only 2 batch calls needed!")
    print(f"⚡ Processing time: ~15 seconds per channel vs immediate individual processing")
    
    # Clean up
    bot_config.cancel_all_batch_timers()


if __name__ == "__main__":
    # Run the demo
    asyncio.run(demo_batch_processing())