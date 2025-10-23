#!/usr/bin/env python3
"""
Test script to verify the refactored moderation processor works correctly.
"""

import sys
sys.path.insert(0, 'src')

from modcord.ai.ai_moderation_processor import ModerationProcessor
from modcord.util.moderation_datatypes import ModerationBatch, ModerationMessage, ModerationImage
from PIL import Image


def test_moderation_processor_init():
    """Test that ModerationProcessor initializes correctly."""
    processor = ModerationProcessor()
    
    assert processor.inference_processor is not None, "Should have inference_processor"
    assert not processor._shutdown, "Should not be shutdown initially"
    
    print("✓ ModerationProcessor initialization test passed")


def test_build_multimodal_messages():
    """Test building multimodal messages with PIL images."""
    processor = ModerationProcessor()
    
    # Create a test batch with mock data
    batch = ModerationBatch(channel_id=123456789)
    
    # Create mock PIL images (1x1 pixel images)
    img1 = Image.new('RGB', (1, 1), color='red')
    img2 = Image.new('RGB', (1, 1), color='blue')
    
    # Add messages with images
    msg1 = ModerationMessage(
        message_id="msg1",
        user_id="user1",
        username="TestUser1",
        content="Test message 1",
        timestamp="2025-10-23T01:00:00Z",
        guild_id=111,
        channel_id=123456789,
        images=[
            ModerationImage(
                attachment_id="att1",
                message_id="msg1",
                user_id="user1",
                index=0,
                filename="test1.png",
                source_url="https://example.com/test1.png",
                pil_image=img1
            )
        ]
    )
    
    msg2 = ModerationMessage(
        message_id="msg2",
        user_id="user2",
        username="TestUser2",
        content="Test message 2",
        timestamp="2025-10-23T01:01:00Z",
        guild_id=111,
        channel_id=123456789,
        images=[
            ModerationImage(
                attachment_id="att2",
                message_id="msg2",
                user_id="user2",
                index=0,
                filename="test2.png",
                source_url="https://example.com/test2.png",
                pil_image=img2
            )
        ]
    )
    
    batch.add_message(msg1)
    batch.add_message(msg2)
    
    # Build multimodal messages
    system_prompt = "You are a helpful assistant."
    messages, user_ids = processor._build_multimodal_messages(system_prompt, batch)
    
    # Verify structure
    assert len(messages) == 2, "Should have system and user messages"
    assert messages[0]["role"] == "system", "First message should be system"
    assert messages[0]["content"] == system_prompt, "System message should have correct content"
    assert messages[1]["role"] == "user", "Second message should be user"
    assert isinstance(messages[1]["content"], list), "User content should be a list"
    
    # Verify content structure
    content_items = messages[1]["content"]
    text_items = [item for item in content_items if item.get("type") == "text"]
    image_items = [item for item in content_items if item.get("type") == "image_pil"]
    
    assert len(text_items) == 1, "Should have one text item"
    assert len(image_items) == 2, "Should have two image items"
    
    # Verify user IDs
    assert len(user_ids) == 2, "Should have two user IDs"
    assert "user1" in user_ids, "Should have user1"
    assert "user2" in user_ids, "Should have user2"
    
    print("✓ Build multimodal messages test passed")
    print(f"  - Generated {len(content_items)} content items (1 text, 2 images)")
    print(f"  - Extracted user IDs: {user_ids}")


def test_api_methods_exist():
    """Test that all expected API methods exist."""
    processor = ModerationProcessor()
    
    # Check that all expected methods exist
    assert hasattr(processor, 'init_model'), "Should have init_model method"
    assert hasattr(processor, 'start_batch_worker'), "Should have start_batch_worker method"
    assert hasattr(processor, 'get_batch_moderation_actions'), "Should have get_batch_moderation_actions method"
    assert hasattr(processor, 'shutdown'), "Should have shutdown method"
    assert hasattr(processor, '_download_images'), "Should have _download_images method"
    assert hasattr(processor, '_build_multimodal_messages'), "Should have _build_multimodal_messages method"
    assert hasattr(processor, '_reconcile_actions'), "Should have _reconcile_actions method"
    
    print("✓ API methods exist test passed")


def main():
    """Run all tests."""
    print("Testing refactored moderation processor...")
    print()
    
    test_moderation_processor_init()
    test_build_multimodal_messages()
    test_api_methods_exist()
    
    print()
    print("=" * 60)
    print("All moderation processor tests passed! ✓")
    print("=" * 60)
    print()
    print("Key improvements:")
    print("  • Images are downloaded and converted to PIL RGB format")
    print("  • Messages include PIL images directly in multimodal content")
    print("  • Dynamic user ID extraction for schema generation")
    print("  • Synchronous LLM calls wrapped in async executors")
    print("  • Simplified message building without extra abstraction")


if __name__ == "__main__":
    main()
