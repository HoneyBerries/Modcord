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


class FakeLLM:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def generate(self, prompts, sampling_params):
        return [SimpleNamespace(outputs=[SimpleNamespace(text=f"reply:{prompt}")]) for prompt in prompts]


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

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    
    # Mock the imports that happen inside init_model
    fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True, device_count=lambda: 1))
    
    # Create a mock for the vllm module
    import sys
    from unittest.mock import MagicMock
    fake_vllm = MagicMock()
    fake_vllm.LLM = FakeLLM
    fake_vllm.SamplingParams = FakeSamplingParams
    
    # Patch sys.modules to inject fake imports
    original_torch = sys.modules.get('torch')
    original_vllm = sys.modules.get('vllm')
    sys.modules['torch'] = fake_torch
    sys.modules['vllm'] = fake_vllm
    
    try:
        processor = ai_core.InferenceProcessor()
        
        # Mock _build_structured_outputs to avoid needing full vllm
        monkeypatch.setattr(processor, "_build_structured_outputs", lambda: None)

        model, params, prompt = await processor.init_model()

        assert isinstance(model, FakeLLM)
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

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    
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
    
    # Create a mock for the vllm module
    import sys
    from unittest.mock import MagicMock
    fake_vllm = MagicMock()
    fake_vllm.LLM = FakeLLM
    fake_vllm.SamplingParams = FakeSamplingParams
    
    # Patch sys.modules to inject fake imports
    original_torch = sys.modules.get('torch')
    original_vllm = sys.modules.get('vllm')
    sys.modules['torch'] = fake_torch
    sys.modules['vllm'] = fake_vllm
    
    try:
        processor = ai_core.InferenceProcessor()
        
        # Mock _build_structured_outputs to avoid needing full vllm
        monkeypatch.setattr(processor, "_build_structured_outputs", lambda: None)
        
        await processor.init_model()
        assert processor.llm is not None

        await processor.unload_model()

        assert processor.llm is None
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
    assert processor.state.init_started is False
    assert processor.state.init_error is None