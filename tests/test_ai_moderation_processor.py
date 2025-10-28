"""Tests for ai_moderation_processor module."""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from modcord.ai.ai_moderation_processor import ModerationProcessor
from modcord.ai.ai_core import InferenceProcessor, ModelState
from modcord.moderation.moderation_datatypes import (
    ModerationChannelBatch,
    ModerationUser,
    ModerationMessage,
    ModerationImage,
    ActionData,
    ActionType,
)


class TestModerationProcessor:
    """Tests for ModerationProcessor class."""

    def test_initialization_default(self):
        """Test ModerationProcessor initialization with default engine."""
        processor = ModerationProcessor()
        assert processor.inference_processor is not None
        assert processor._shutdown is False

    def test_initialization_custom_engine(self):
        """Test ModerationProcessor initialization with custom engine."""
        mock_engine = Mock(spec=InferenceProcessor)
        processor = ModerationProcessor(engine=mock_engine)
        assert processor.inference_processor is mock_engine
        assert processor._shutdown is False

    @pytest.mark.asyncio
    async def test_init_model_success(self):
        """Test init_model returns True on success."""
        mock_engine = Mock(spec=InferenceProcessor)
        mock_engine.init_model = AsyncMock(return_value=True)
        mock_engine.state = ModelState(available=True)
        
        processor = ModerationProcessor(engine=mock_engine)
        result = await processor.init_model()
        
        assert result is True
        assert processor._shutdown is False
        mock_engine.init_model.assert_called_once()

    @pytest.mark.asyncio
    async def test_init_model_failure(self):
        """Test init_model returns False on failure."""
        mock_engine = Mock(spec=InferenceProcessor)
        mock_engine.init_model = AsyncMock(return_value=False)
        mock_engine.state = ModelState(init_error="Test error")
        
        processor = ModerationProcessor(engine=mock_engine)
        result = await processor.init_model()
        
        assert result is False
        mock_engine.init_model.assert_called_once()

    @pytest.mark.asyncio
    async def test_init_model_with_custom_model(self):
        """Test init_model passes model parameter."""
        mock_engine = Mock(spec=InferenceProcessor)
        mock_engine.init_model = AsyncMock(return_value=True)
        mock_engine.state = ModelState(available=True)
        
        processor = ModerationProcessor(engine=mock_engine)
        result = await processor.init_model(model="custom-model")
        
        assert result is True
        mock_engine.init_model.assert_called_once_with("custom-model")

    @pytest.mark.asyncio
    async def test_start_batch_worker_success(self):
        """Test start_batch_worker returns True when model initialized."""
        mock_engine = Mock(spec=InferenceProcessor)
        mock_engine.state = ModelState(available=True)
        
        processor = ModerationProcessor(engine=mock_engine)
        with patch.object(processor, '_ensure_model_initialized', return_value=True):
            result = await processor.start_batch_worker()
            assert result is True

    @pytest.mark.asyncio
    async def test_start_batch_worker_failure(self):
        """Test start_batch_worker returns False when model not initialized."""
        mock_engine = Mock(spec=InferenceProcessor)
        mock_engine.state = ModelState(available=False)
        
        processor = ModerationProcessor(engine=mock_engine)
        with patch.object(processor, '_ensure_model_initialized', return_value=False):
            result = await processor.start_batch_worker()
            assert result is False

    @pytest.mark.asyncio
    async def test_get_multi_batch_moderation_actions_empty_batches(self):
        """Test get_multi_batch_moderation_actions returns empty dict for no batches."""
        processor = ModerationProcessor()
        result = await processor.get_multi_batch_moderation_actions([])
        assert result == {}

    def test_batch_to_json_with_images_basic(self):
        """Test _batch_to_json_with_images with basic batch."""
        processor = ModerationProcessor()
        
        timestamp = datetime.now(timezone.utc).isoformat()
        msg = ModerationMessage(
            message_id="123",
            user_id="456",
            content="Test message",
            timestamp=timestamp,
            guild_id=789,
            channel_id=111
        )
        
        user = ModerationUser(
            user_id="456",
            username="TestUser",
            messages=[msg]
        )
        
        batch = ModerationChannelBatch(
            channel_id=111,
            channel_name="general",
            users=[user]
        )
        
        payload, pil_images, image_map = processor._batch_to_json_with_images(batch)
        
        assert payload["channel_id"] == "111"
        assert payload["channel_name"] == "general"
        assert payload["message_count"] == 1
        assert payload["unique_user_count"] == 1
        assert payload["total_images"] == 0
        assert len(payload["users"]) == 1
        assert payload["users"][0]["user_id"] == "456"
        assert len(pil_images) == 0

    def test_batch_to_json_with_images_with_history(self):
        """Test _batch_to_json_with_images includes history users."""
        processor = ModerationProcessor()
        
        timestamp = datetime.now(timezone.utc).isoformat()
        msg1 = ModerationMessage(
            message_id="123",
            user_id="456",
            content="Current message",
            timestamp=timestamp,
            guild_id=789,
            channel_id=111
        )
        
        msg2 = ModerationMessage(
            message_id="124",
            user_id="457",
            content="History message",
            timestamp=timestamp,
            guild_id=789,
            channel_id=111
        )
        
        user1 = ModerationUser(user_id="456", username="User1", messages=[msg1])
        user2 = ModerationUser(user_id="457", username="User2", messages=[msg2])
        
        batch = ModerationChannelBatch(
            channel_id=111,
            channel_name="general",
            users=[user1],
            history_users=[user2]
        )
        
        payload, pil_images, image_map = processor._batch_to_json_with_images(batch)
        
        assert payload["unique_user_count"] == 2
        assert payload["message_count"] == 2
        assert len(payload["users"]) == 2

    def test_batch_to_json_with_images_with_pil_images(self):
        """Test _batch_to_json_with_images handles PIL images."""
        processor = ModerationProcessor()
        
        mock_pil = MagicMock()
        img = ModerationImage(
            image_id="img123",
            pil_image=mock_pil
        )
        
        timestamp = datetime.now(timezone.utc).isoformat()
        msg = ModerationMessage(
            message_id="123",
            user_id="456",
            content="",
            timestamp=timestamp,
            guild_id=789,
            channel_id=111,
            images=[img]
        )
        
        user = ModerationUser(user_id="456", username="User", messages=[msg])
        batch = ModerationChannelBatch(channel_id=111, channel_name="general", users=[user])
        
        payload, pil_images, image_map = processor._batch_to_json_with_images(batch)
        
        assert payload["total_images"] == 1
        assert len(pil_images) == 1
        assert pil_images[0] is mock_pil
        assert "img123" in image_map
        assert image_map["img123"] == 0
        
        # Check message has image_id
        user_data = payload["users"][0]
        msg_data = user_data["messages"][0]
        assert "img123" in msg_data["image_ids"]

    def test_batch_to_json_with_images_empty_content(self):
        """Test _batch_to_json_with_images handles empty content with images."""
        processor = ModerationProcessor()
        
        mock_pil = MagicMock()
        img = ModerationImage(
            image_id="img1",
            pil_image=mock_pil
        )
        
        timestamp = datetime.now(timezone.utc).isoformat()
        msg = ModerationMessage(
            message_id="123",
            user_id="456",
            content="",
            timestamp=timestamp,
            guild_id=789,
            channel_id=111,
            images=[img]
        )
        
        user = ModerationUser(user_id="456", username="User", messages=[msg])
        batch = ModerationChannelBatch(channel_id=111, channel_name="general", users=[user])
        
        payload, _, _ = processor._batch_to_json_with_images(batch)
        
        user_data = payload["users"][0]
        msg_data = user_data["messages"][0]
        assert msg_data["content"] == "[Images only]"

    def test_format_multimodal_messages_text_only(self):
        """Test _format_multimodal_messages with text only."""
        processor = ModerationProcessor()
        
        system_prompt = "Test system prompt"
        json_payload = {"test": "data"}
        pil_images = []
        
        result = processor._format_multimodal_messages(
            system_prompt,
            json_payload,
            pil_images
        )
        
        assert len(result) == 2
        assert result[0]["role"] == "system"
        assert result[0]["content"] == system_prompt
        assert result[1]["role"] == "user"
        assert isinstance(result[1]["content"], list)
        assert result[1]["content"][0]["type"] == "text"

    def test_format_multimodal_messages_with_images(self):
        """Test _format_multimodal_messages with images."""
        processor = ModerationProcessor()
        
        system_prompt = "Test prompt"
        json_payload = {"test": "data"}
        mock_pil = MagicMock()
        pil_images = [mock_pil]
        
        result = processor._format_multimodal_messages(
            system_prompt,
            json_payload,
            pil_images
        )
        
        assert len(result) == 2
        assert result[1]["role"] == "user"
        content = result[1]["content"]
        assert len(content) == 2  # text + 1 image
        assert content[0]["type"] == "text"
        assert content[1]["type"] == "image_pil"
        assert content[1]["image_pil"] is mock_pil

    def test_resolve_server_rules_empty(self):
        """Test _resolve_server_rules with empty input."""
        processor = ModerationProcessor()
        with patch('modcord.ai.ai_moderation_processor.app_config') as mock_config:
            mock_config.server_rules = ""
            result = processor._resolve_server_rules("")
            assert result == ""

    def test_resolve_server_rules_with_content(self):
        """Test _resolve_server_rules with content."""
        processor = ModerationProcessor()
        with patch('modcord.ai.ai_moderation_processor.app_config') as mock_config:
            mock_config.server_rules = ""
            result = processor._resolve_server_rules("No spam allowed")
            assert result == "No spam allowed"

    def test_resolve_channel_guidelines_empty(self):
        """Test _resolve_channel_guidelines with empty input."""
        processor = ModerationProcessor()
        with patch('modcord.ai.ai_moderation_processor.app_config') as mock_config:
            mock_config.channel_guidelines = ""
            result = processor._resolve_channel_guidelines("")
            assert result == ""

    def test_resolve_channel_guidelines_with_content(self):
        """Test _resolve_channel_guidelines with content."""
        processor = ModerationProcessor()
        with patch('modcord.ai.ai_moderation_processor.app_config') as mock_config:
            mock_config.channel_guidelines = ""
            result = processor._resolve_channel_guidelines("Be respectful")
            assert result == "Be respectful"
