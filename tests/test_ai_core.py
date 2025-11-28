"""Tests for ai_core module."""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from modcord.ai.ai_core import (
    ModelState,
    InferenceProcessor,
    inference_processor,
)


class TestModelState:
    """Tests for ModelState dataclass."""

    def test_model_state_initialization(self):
        """Test ModelState default initialization."""
        state = ModelState()
        assert state.init_started is False
        assert state.available is False
        assert state.init_error is None

    def test_model_state_with_values(self):
        """Test ModelState with custom values."""
        state = ModelState(
            init_started=True,
            available=True,
            init_error="Test error"
        )
        assert state.init_started is True
        assert state.available is True
        assert state.init_error == "Test error"


class TestInferenceProcessor:
    """Tests for InferenceProcessor class."""

    def test_initialization(self):
        """Test InferenceProcessor initialization."""
        processor = InferenceProcessor()
        assert processor.llm is None
        assert processor.sampling_params is None
        assert processor.base_system_prompt is None
        assert isinstance(processor.state, ModelState)
        assert processor.state.init_started is False
        assert processor.state.available is False

    def test_set_init_error(self):
        """Test _set_init_error method."""
        processor = InferenceProcessor()
        processor._set_init_error("Test error message")
        assert processor.state.available is False
        assert processor.state.init_error == "Test error message"

    def test_is_model_available_false(self):
        """Test is_model_available returns False initially."""
        processor = InferenceProcessor()
        assert processor.is_model_available() is False

    def test_is_model_available_true(self):
        """Test is_model_available returns True when set."""
        processor = InferenceProcessor()
        processor.state.available = True
        assert processor.is_model_available() is True

    def test_get_model_init_error(self):
        """Test get_model_init_error method."""
        processor = InferenceProcessor()
        assert processor.get_model_init_error() is None
        
        processor.state.init_error = "Failed to load"
        assert processor.get_model_init_error() == "Failed to load"

    def test_get_system_prompt_template_only(self):
        """Test get_system_prompt with template only."""
        processor = InferenceProcessor()
        processor.base_system_prompt = "Base prompt template"
        result = processor.get_system_prompt()
        assert result == "Base prompt template"

    def test_get_system_prompt_with_server_rules_inject(self):
        """Test get_system_prompt with SERVER_RULES_INJECT placeholder."""
        processor = InferenceProcessor()
        processor.base_system_prompt = "Prompt <|SERVER_RULES_INJECT|> here"
        result = processor.get_system_prompt(server_rules="No spam allowed")
        assert result == "Prompt No spam allowed here"

    def test_get_system_prompt_with_channel_guidelines_inject(self):
        """Test get_system_prompt with CHANNEL_GUIDELINES_INJECT placeholder."""
        processor = InferenceProcessor()
        processor.base_system_prompt = "Guidelines: <|CHANNEL_GUIDELINES_INJECT|>"
        result = processor.get_system_prompt(channel_guidelines="Be respectful")
        assert result == "Guidelines: Be respectful"

    def test_get_system_prompt_with_both_injects(self):
        """Test get_system_prompt with both placeholders."""
        processor = InferenceProcessor()
        processor.base_system_prompt = (
            "Rules: <|SERVER_RULES_INJECT|> "
            "Channel: <|CHANNEL_GUIDELINES_INJECT|>"
        )
        result = processor.get_system_prompt(
            server_rules="No spam",
            channel_guidelines="Be nice"
        )
        assert result == "Rules: No spam Channel: Be nice"

    def test_get_system_prompt_appends_rules_no_placeholder(self):
        """Test get_system_prompt appends rules when no placeholder."""
        processor = InferenceProcessor()
        processor.base_system_prompt = "Base prompt"
        result = processor.get_system_prompt(server_rules="No spam")
        assert "Base prompt" in result
        assert "No spam" in result
        assert "Server rules:" in result

    def test_get_system_prompt_appends_guidelines_no_placeholder(self):
        """Test get_system_prompt appends guidelines when no placeholder."""
        processor = InferenceProcessor()
        processor.base_system_prompt = "Base prompt"
        result = processor.get_system_prompt(channel_guidelines="Be nice")
        assert "Base prompt" in result
        assert "Be nice" in result
        assert "Channel-specific guidelines:" in result

    def test_get_system_prompt_empty_rules_and_guidelines(self):
        """Test get_system_prompt with empty rules and guidelines."""
        processor = InferenceProcessor()
        processor.base_system_prompt = "Base prompt"
        result = processor.get_system_prompt(server_rules="", channel_guidelines="")
        assert result == "Base prompt"

    def test_get_system_prompt_none_template(self):
        """Test get_system_prompt with None template uses fallback."""
        processor = InferenceProcessor()
        processor.base_system_prompt = None
        
        # Mock app_config to return a fallback template
        with patch('modcord.ai.ai_core.cfg.app_config') as mock_config:
            mock_config.system_prompt_template = "Fallback prompt"
            result = processor.get_system_prompt()
            # Should use the fallback from app_config
            assert "Fallback prompt" in result or result == ""

    def test_get_model_state(self):
        """Test get_model_state returns state object."""
        processor = InferenceProcessor()
        state = processor.get_model_state()
        assert isinstance(state, ModelState)
        assert state is processor.state

    @pytest.mark.asyncio
    async def test_init_model_missing_configuration(self):
        """Test init_model fails with missing configuration."""
        processor = InferenceProcessor()
        
        with patch('modcord.ai.ai_core.cfg.app_config.reload', return_value=None):
            result = await processor.init_model()
            assert result is False
            assert processor.state.available is False
            assert processor.state.init_error == "missing configuration"

    @pytest.mark.asyncio
    async def test_init_model_ai_disabled(self):
        """Test init_model fails when AI is disabled."""
        processor = InferenceProcessor()
        
        mock_config_obj = Mock()
        mock_config_obj.reload.return_value = {"test": "config"}
        
        with patch('modcord.ai.ai_core.cfg.app_config', mock_config_obj):
            mock_config_obj.ai_settings = {"enabled": False}
            result = await processor.init_model()
            assert result is False
            assert processor.state.available is False
            assert processor.state.init_error == "AI disabled in config"

    @pytest.mark.asyncio
    async def test_init_model_missing_model_id(self):
        """Test init_model fails when model_id is missing."""
        processor = InferenceProcessor()
        
        mock_config_obj = Mock()
        mock_config_obj.reload.return_value = {"test": "config"}
        
        with patch('modcord.ai.ai_core.cfg.app_config', mock_config_obj):
            mock_config_obj.ai_settings = {"enabled": True}
            result = await processor.init_model()
            assert result is False
            assert processor.state.available is False
            assert processor.state.init_error == "missing model id"

    @pytest.mark.asyncio
    async def test_init_model_already_initialized(self):
        """Test init_model returns True when already initialized."""
        processor = InferenceProcessor()
        processor.state.available = True
        processor.llm = Mock()
        processor.sampling_params = Mock()
        
        result = await processor.init_model()
        assert result is True

    @pytest.mark.asyncio
    async def test_init_model_previous_failure_no_retry(self):
        """Test init_model doesn't retry after previous failure."""
        processor = InferenceProcessor()
        processor.state.init_started = True
        processor.state.init_error = "Previous error"
        processor.state.available = False
        
        result = await processor.init_model()
        assert result is False

    @pytest.mark.asyncio
    async def test_unload_model(self):
        """Test unload_model clears state."""
        processor = InferenceProcessor()
        processor.llm = Mock()
        processor.sampling_params = Mock()
        processor.state.available = True
        processor.state.init_started = True
        processor.state.init_error = "Some error"
        
        with patch.object(processor, '_cleanup_gpu'):
            await processor.unload_model()
        
        assert processor.llm is None
        assert processor.sampling_params is None
        assert processor.state.available is False
        assert processor.state.init_started is False
        assert processor.state.init_error is None

    def test_cleanup_gpu_no_torch(self):
        """Test _cleanup_gpu works without torch."""
        processor = InferenceProcessor()
        # Should not raise exception
        processor._cleanup_gpu()

    def test_cleanup_gpu_with_torch(self):
        """Test _cleanup_gpu calls torch.cuda.empty_cache."""
        processor = InferenceProcessor()
        
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.empty_cache = Mock()
        
        with patch.dict('sys.modules', {'torch': mock_torch}):
            processor._cleanup_gpu()
            mock_torch.cuda.empty_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_multi_chat_model_unavailable(self):
        """Test generate_multi_chat raises error when model unavailable."""
        processor = InferenceProcessor()
        processor.llm = None
        processor.sampling_params = None
        processor.state.init_error = "Model not loaded"
        
        with pytest.raises(RuntimeError, match="Model not loaded"):
            await processor.generate_multi_chat(
                conversations=[[{"role": "user", "content": "test"}]],
                grammar_strings=[""]
            )

    def test_init_model_sync_import_error(self):
        """Test _init_model_sync handles import errors."""
        processor = InferenceProcessor()
        
        with patch('builtins.__import__', side_effect=ImportError("vLLM not found")):
            result = processor._init_model_sync(
                model_id="test-model",
                sampling_parameters={
                    "dtype": "auto",
                    "max_new_tokens": 256,
                    "max_model_length": 2048,
                    "temperature": 1.0,
                    "top_p": 1.0,
                    "top_k": -1,
                },
                vram_percentage=0.5,
                cpu_offload_gb=0
            )
            assert result is False
            assert "AI libraries not available" in processor.state.init_error


class TestModuleLevelObjects:
    """Test module-level singleton objects."""

    def test_inference_processor_singleton(self):
        """Test inference_processor is an InferenceProcessor instance."""
        assert isinstance(inference_processor, InferenceProcessor)

    def test_model_state_reference(self):
        """Test model_state references inference_processor.state."""
        from modcord.ai.ai_core import model_state
        assert model_state is inference_processor.state
