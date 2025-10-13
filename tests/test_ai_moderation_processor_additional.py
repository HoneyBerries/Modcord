import json
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest

from modcord.ai import ai_core
from modcord.ai.ai_moderation_processor import ModerationProcessor
from modcord.util.moderation_datatypes import ActionType, ModerationBatch, ModerationMessage


class FakeState:
    def __init__(self) -> None:
        self.init_started = True
        self.available = True
        self.init_error: str | None = None


class FakeEngine:
    def __init__(self) -> None:
        self.state = FakeState()
        self.llm = object()
        self.sampling_params = object()
        self.system_prompt_calls: list[str] = []

    async def init_model(self, model=None):
        self.state.init_started = True
        return True

    async def get_model(self):
        return self.llm, self.sampling_params, "prompt"

    async def get_system_prompt(self, server_rules: str = "") -> str:
        self.system_prompt_calls.append(server_rules)
        return f"SYSTEM:{server_rules}"


@pytest.fixture(autouse=True)
def patch_app_config(monkeypatch):
    fake_app_config = SimpleNamespace(ai_settings=SimpleNamespace(batching={}))
    monkeypatch.setattr(
        "modcord.ai.ai_moderation_processor.app_config",
        fake_app_config,
        raising=False,
    )
    yield


@pytest.mark.asyncio
async def test_submit_inference_returns_shutdown_message(monkeypatch):
    processor = ModerationProcessor(engine=cast(ai_core.InferenceProcessor, FakeEngine()))
    processor._shutdown = True

    result = await processor.submit_inference([{"role": "user", "content": "hi"}])

    assert result == "null: shutting down"


@pytest.mark.asyncio
async def test_submit_inference_handles_unavailable_model(monkeypatch):
    engine = FakeEngine()
    engine.state.available = False
    engine.state.init_error = "model offline"

    processor = ModerationProcessor()
    processor.inference_processor = cast(ai_core.InferenceProcessor, engine)

    result = await processor.submit_inference([{"role": "user", "content": "hi"}])

    assert result == "null: model offline"


@pytest.mark.asyncio
async def test_submit_inference_success(monkeypatch):
    engine = FakeEngine()
    processor = ModerationProcessor()
    processor.inference_processor = cast(ai_core.InferenceProcessor, engine)

    async def fake_enqueue(prompt: str) -> str:
        return f"response:{prompt}"

    monkeypatch.setattr(processor, "_ensure_inference_batch_worker", lambda: None)
    monkeypatch.setattr(processor, "_enqueue_prompt_for_inference", fake_enqueue)

    result = await processor.submit_inference([{"role": "user", "content": "payload"}])

    assert result.startswith("response:")
    assert "payload" in result


@pytest.mark.asyncio
async def test_submit_inference_handles_get_model_error(monkeypatch):
    engine = FakeEngine()
    processor = ModerationProcessor()
    processor.inference_processor = cast(ai_core.InferenceProcessor, engine)

    engine.get_model = AsyncMock(side_effect=RuntimeError("boom"))

    result = await processor.submit_inference([{"role": "user", "content": "payload"}])

    assert result == "null: inference error"


@pytest.mark.asyncio
async def test_submit_inference_detects_unready_model(monkeypatch):
    engine = FakeEngine()
    engine.llm = None
    engine.sampling_params = None
    processor = ModerationProcessor()
    processor.inference_processor = cast(ai_core.InferenceProcessor, engine)

    result = await processor.submit_inference([{"role": "user", "content": "payload"}])

    assert result == "null: AI model unavailable"


@pytest.mark.asyncio
async def test_submit_inference_handles_empty_enqueue_response(monkeypatch):
    engine = FakeEngine()
    processor = ModerationProcessor()
    processor.inference_processor = cast(ai_core.InferenceProcessor, engine)

    monkeypatch.setattr(processor, "_ensure_inference_batch_worker", lambda: None)
    monkeypatch.setattr(processor, "_enqueue_prompt_for_inference", AsyncMock(return_value=""))

    result = await processor.submit_inference([{"role": "user", "content": "payload"}])

    assert result == "null: no response"


@pytest.mark.asyncio
async def test_submit_inference_handles_runtime_error(monkeypatch):
    engine = FakeEngine()
    processor = ModerationProcessor()
    processor.inference_processor = cast(ai_core.InferenceProcessor, engine)

    monkeypatch.setattr(processor, "_ensure_inference_batch_worker", lambda: None)
    monkeypatch.setattr(processor, "_enqueue_prompt_for_inference", AsyncMock(side_effect=RuntimeError("queue full")))

    result = await processor.submit_inference([{"role": "user", "content": "payload"}])

    assert result == "null: queue full"


@pytest.mark.asyncio
async def test_submit_inference_handles_generic_error(monkeypatch):
    engine = FakeEngine()
    processor = ModerationProcessor()
    processor.inference_processor = cast(ai_core.InferenceProcessor, engine)

    monkeypatch.setattr(processor, "_ensure_inference_batch_worker", lambda: None)
    monkeypatch.setattr(processor, "_enqueue_prompt_for_inference", AsyncMock(side_effect=ValueError("broken")))

    result = await processor.submit_inference([{"role": "user", "content": "payload"}])

    assert result == "null: inference error"


@pytest.mark.asyncio
async def test_get_batch_moderation_actions_merges_duplicate_users(monkeypatch):
    engine = FakeEngine()
    processor = ModerationProcessor()
    processor.inference_processor = cast(ai_core.InferenceProcessor, engine)

    async def fake_submit(messages):
        payload = {
            "channel_id": "123",
            "users": [
                {
                    "user_id": "42",
                    "action": "timeout",
                    "reason": "Repeated spam",
                    "message_ids_to_delete": ["m1"],
                    "timeout_duration": 600,
                    "ban_duration": None,
                },
                {
                    "user_id": "42",
                    "action": "null",
                    "reason": "",
                    "message_ids_to_delete": ["m2"],
                    "timeout_duration": None,
                    "ban_duration": None,
                },
                {
                    "user_id": "99",
                    "action": "warn",
                    "reason": "Language",
                    "message_ids_to_delete": [],
                    "timeout_duration": None,
                    "ban_duration": None,
                },
            ],
        }
        return json.dumps(payload)

    monkeypatch.setattr(processor, "submit_inference", fake_submit)

    batch = ModerationBatch(channel_id=123)
    batch.add_message(
        ModerationMessage(
            message_id="m1",
            user_id="42",
            username="alice",
            content="hello",
            timestamp="2024-01-01T00:00:00Z",
            guild_id=1,
            channel_id=123,
        )
    )
    batch.add_message(
        ModerationMessage(
            message_id="m2",
            user_id="42",
            username="alice",
            content="again",
            timestamp="2024-01-01T00:00:01Z",
            guild_id=1,
            channel_id=123,
        )
    )
    batch.add_message(
        ModerationMessage(
            message_id="m3",
            user_id="99",
            username="bob",
            content="hey",
            timestamp="2024-01-01T00:00:02Z",
            guild_id=1,
            channel_id=123,
        )
    )

    actions = await processor.get_batch_moderation_actions(batch, server_rules="Be kind")

    assert len(actions) == 2

    timeout_action = next(a for a in actions if a.user_id == "42")
    assert timeout_action.action is ActionType.TIMEOUT
    assert set(timeout_action.message_ids) == {"m1", "m2"}
    assert timeout_action.timeout_duration == 600

    warn_action = next(a for a in actions if a.user_id == "99")
    assert warn_action.action is ActionType.WARN
    assert warn_action.message_ids == ["m3"]
    assert warn_action.reason == "Language"


def test_messages_to_prompt_formats_roles():
    processor = ModerationProcessor()
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "assistant", "content": "assistant reply"},
        {"role": "user", "content": "hello"},
        {"role": "other", "content": "fallback"},
    ]

    prompt = processor.messages_to_prompt(messages)

    assert "[SYSTEM]\nsys" in prompt
    assert "[ASSISTANT]\nassistant reply" in prompt
    assert prompt.endswith("[USER]\nfallback")
