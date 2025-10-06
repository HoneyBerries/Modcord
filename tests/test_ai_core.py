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
    monkeypatch.setattr(ai_core, "LLM", FakeLLM)
    monkeypatch.setattr(ai_core, "SamplingParams", FakeSamplingParams)
    monkeypatch.setattr(ai_core.InferenceProcessor, "_build_guided_decoding", lambda self: "grammar")
    monkeypatch.setattr(ai_core.torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(ai_core.torch.cuda, "device_count", lambda: 1)

    processor = ai_core.InferenceProcessor()

    model, params, prompt = await processor.init_model()

    assert isinstance(model, FakeLLM)
    assert isinstance(params, FakeSamplingParams)
    assert prompt == fake_config.system_prompt_template
    assert processor.state.available is True

    responses = await processor.generate_text(["hello", "world"])

    assert responses == ["reply:hello", "reply:world"]


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
    monkeypatch.setattr(ai_core, "LLM", FakeLLM)
    monkeypatch.setattr(ai_core, "SamplingParams", FakeSamplingParams)
    monkeypatch.setattr(ai_core.InferenceProcessor, "_build_guided_decoding", lambda self: "grammar")

    monkeypatch.setattr(ai_core.torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr(ai_core.torch.cuda, "synchronize", lambda: None)
    monkeypatch.setattr(ai_core.torch.cuda, "empty_cache", lambda: None)
    monkeypatch.setattr(ai_core.torch.cuda, "ipc_collect", lambda: None)

    fake_dist = SimpleNamespace(
        is_available=lambda: True,
        is_initialized=lambda: True,
        destroy_process_group=lambda group=None: None,
        group=SimpleNamespace(WORLD=object()),
    )
    monkeypatch.setattr(ai_core.torch, "distributed", fake_dist, raising=False)

    processor = ai_core.InferenceProcessor()
    await processor.init_model()
    assert processor.llm is not None

    await processor.unload_model()

    assert processor.llm is None
    assert processor.state.available is False
    assert processor.state.init_started is False
    assert processor.state.init_error is None