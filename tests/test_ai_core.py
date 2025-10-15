import asyncio
from types import SimpleNamespace

import pytest

from modcord.ai import ai_core


class FakeConfig:
    def __init__(self, reload_payload, ai_settings, system_prompt="SYSTEM") -> None:
        self._reload_payload = reload_payload
        self._ai_settings = ai_settings
        self.system_prompt_template = system_prompt

    def reload(self):
        return self._reload_payload

    @property
    def ai_settings(self):
        return self._ai_settings

    def format_system_prompt(self, server_rules: str, *, template_override=None) -> str:
        template = template_override or self.system_prompt_template
        return template.replace("{SERVER_RULES}", server_rules)


class FakeSamplingParams:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


class FakeAsyncLLMEngine:
    """Mock AsyncLLMEngine that simulates async generation."""
    
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self._shutdown_called = False

    async def generate(self, prompt, sampling_params, request_id, **kwargs):
        """Async generator that yields a single RequestOutput."""
        # Simulate async generation by yielding a final output
        output = SimpleNamespace(
            outputs=[SimpleNamespace(text=f"reply:{prompt}")]
        )
        yield output

    async def shutdown(self):
        """Mock shutdown method."""
        self._shutdown_called = True


class FakeAsyncEngineArgs:
    """Mock AsyncEngineArgs."""
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


@pytest.mark.asyncio
async def test_init_model_missing_configuration(monkeypatch):
    fake_config = FakeConfig(reload_payload={}, ai_settings={})
    monkeypatch.setattr(ai_core.cfg, "app_config", fake_config)

    processor = ai_core.InferenceProcessor()

    model, params, prompt = await processor.init_model()

    assert model is None and params is None and prompt is None
    assert processor.state.available is False
    assert processor.state.init_error == "missing configuration"


@pytest.mark.asyncio
async def test_init_model_disabled_returns_prompt(monkeypatch):
    ai_settings = {"enabled": False, "model_id": "model", "allow_gpu": False}
    fake_config = FakeConfig(reload_payload={"ok": True}, ai_settings=ai_settings)
    monkeypatch.setattr(ai_core.cfg, "app_config", fake_config)

    processor = ai_core.InferenceProcessor()

    model, params, prompt = await processor.init_model()

    assert model is None and params is None
    assert prompt == fake_config.system_prompt_template
    assert processor.state.available is False
    assert processor.state.init_error == "AI disabled in config"


@pytest.mark.asyncio
async def test_init_model_success_and_generate_text(monkeypatch):
    ai_settings = {
        "enabled": True,
        "allow_gpu": True,
        "vram_percentage": 0.5,
        "model_id": "fake-model",
        "knobs": {
            "dtype": "auto",
            "max_new_tokens": 16,
            "max_model_length": 512,
            "temperature": 0.7,
            "top_p": 0.9,
            "top_k": 10,
            "repetition_penalty": 1.0,
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0,
        },
    }
    fake_config = FakeConfig(reload_payload={"ok": True}, ai_settings=ai_settings)
    monkeypatch.setattr(ai_core.cfg, "app_config", fake_config)
    
    # Mock the imports that happen inside init_model
    fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True, device_count=lambda: 1))
    
    # Create a mock for the vllm module with AsyncLLMEngine
    import sys
    from unittest.mock import MagicMock, AsyncMock
    
    fake_async_llm_engine_module = MagicMock()
    fake_async_llm_engine_module.AsyncLLMEngine = FakeAsyncLLMEngine
    # Mock the from_engine_args class method (it's synchronous, not async)
    def mock_from_engine_args(engine_args, **kwargs):
        return FakeAsyncLLMEngine(**engine_args.kwargs)
    FakeAsyncLLMEngine.from_engine_args = staticmethod(mock_from_engine_args) # type: ignore
    
    fake_arg_utils = MagicMock()
    fake_arg_utils.AsyncEngineArgs = FakeAsyncEngineArgs
    
    fake_vllm = MagicMock()
    fake_vllm.SamplingParams = FakeSamplingParams
    
    # Patch sys.modules to inject fake imports
    original_torch = sys.modules.get('torch')
    original_vllm = sys.modules.get('vllm')
    original_async_llm = sys.modules.get('vllm.engine.async_llm_engine')
    original_arg_utils = sys.modules.get('vllm.engine.arg_utils')
    
    sys.modules['torch'] = fake_torch # type: ignore
    sys.modules['vllm'] = fake_vllm
    sys.modules['vllm.engine.async_llm_engine'] = fake_async_llm_engine_module
    sys.modules['vllm.engine.arg_utils'] = fake_arg_utils
    
    try:
        processor = ai_core.InferenceProcessor()
        
        # Mock _build_structured_outputs to avoid needing full vllm
        monkeypatch.setattr(processor, "_build_structured_outputs", lambda: None)

        engine, params, prompt = await processor.init_model()

        assert isinstance(engine, FakeAsyncLLMEngine)
        assert isinstance(params, FakeSamplingParams)
        assert prompt == fake_config.system_prompt_template
        assert processor.state.available is True

        responses = await processor.generate_text(["hello", "world"])

        assert responses == ["reply:hello", "reply:world"]
    finally:
        # Restore original modules
        if original_torch is not None:
            sys.modules['torch'] = original_torch
        else:
            sys.modules.pop('torch', None)
        if original_vllm is not None:
            sys.modules['vllm'] = original_vllm
        else:
            sys.modules.pop('vllm', None)
        if original_async_llm is not None:
            sys.modules['vllm.engine.async_llm_engine'] = original_async_llm
        else:
            sys.modules.pop('vllm.engine.async_llm_engine', None)
        if original_arg_utils is not None:
            sys.modules['vllm.engine.arg_utils'] = original_arg_utils
        else:
            sys.modules.pop('vllm.engine.arg_utils', None)


@pytest.mark.asyncio
async def test_unload_model_resets_state(monkeypatch):
    ai_settings = {
        "enabled": True,
        "allow_gpu": False,
        "model_id": "fake-model",
        "knobs": {},
    }
    fake_config = FakeConfig(reload_payload={"ok": True}, ai_settings=ai_settings)
    monkeypatch.setattr(ai_core.cfg, "app_config", fake_config)
    
    # Mock the imports that happen inside init_model
    fake_dist = SimpleNamespace(
        is_available=lambda: True,
        is_initialized=lambda: True,
        destroy_process_group=lambda group=None: None,
        group=SimpleNamespace(WORLD=object()),
    )
    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(
            is_available=lambda: False,
            synchronize=lambda: None,
            empty_cache=lambda: None,
            ipc_collect=lambda: None,
        ),
        distributed=fake_dist
    )
    
    # Create a mock for the vllm module with AsyncLLMEngine
    import sys
    from unittest.mock import MagicMock
    
    fake_async_llm_engine_module = MagicMock()
    fake_async_llm_engine_module.AsyncLLMEngine = FakeAsyncLLMEngine
    # Mock the from_engine_args class method (it's synchronous, not async)
    def mock_from_engine_args(engine_args, **kwargs):
        return FakeAsyncLLMEngine(**engine_args.kwargs)
    FakeAsyncLLMEngine.from_engine_args = staticmethod(mock_from_engine_args) # type: ignore
    
    fake_arg_utils = MagicMock()
    fake_arg_utils.AsyncEngineArgs = FakeAsyncEngineArgs
    
    fake_vllm = MagicMock()
    fake_vllm.SamplingParams = FakeSamplingParams
    
    # Patch sys.modules to inject fake imports
    original_torch = sys.modules.get('torch')
    original_vllm = sys.modules.get('vllm')
    original_async_llm = sys.modules.get('vllm.engine.async_llm_engine')
    original_arg_utils = sys.modules.get('vllm.engine.arg_utils')
    
    sys.modules['torch'] = fake_torch # type: ignore
    sys.modules['vllm'] = fake_vllm
    sys.modules['vllm.engine.async_llm_engine'] = fake_async_llm_engine_module
    sys.modules['vllm.engine.arg_utils'] = fake_arg_utils
    
    try:
        processor = ai_core.InferenceProcessor()
        
        # Mock _build_structured_outputs to avoid needing full vllm
        monkeypatch.setattr(processor, "_build_structured_outputs", lambda: None)
        
        await processor.init_model()
        assert processor.engine is not None

        await processor.unload_model()

        assert processor.engine is None
        assert processor.state.available is False
    finally:
        # Restore original modules
        if original_torch is not None:
            sys.modules['torch'] = original_torch
        else:
            sys.modules.pop('torch', None)
        if original_vllm is not None:
            sys.modules['vllm'] = original_vllm
        else:
            sys.modules.pop('vllm', None)
        if original_async_llm is not None:
            sys.modules['vllm.engine.async_llm_engine'] = original_async_llm
        else:
            sys.modules.pop('vllm.engine.async_llm_engine', None)
        if original_arg_utils is not None:
            sys.modules['vllm.engine.arg_utils'] = original_arg_utils
        else:
            sys.modules.pop('vllm.engine.arg_utils', None)
    assert processor.state.init_started is False
    assert processor.state.init_error is None