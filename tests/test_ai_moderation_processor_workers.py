import asyncio
import json
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest

from modcord.ai import ai_core
from modcord.ai.ai_moderation_processor import ModerationProcessor
from modcord.util.moderation_datatypes import ActionType, ModerationMessage
import modcord.util.moderation_parsing as moderation_parsing


class DummyState:
    def __init__(self) -> None:
        self.init_started = False
        self.available = True
        self.init_error: str | None = None


class DummyEngine:
    def __init__(self) -> None:
        self.state = DummyState()
        self.llm = object()
        self.sampling_params = object()
        self.warmup_completed = False

    async def init_model(self, model: str | None = None) -> bool:
        self.state.init_started = True
        return True

    async def get_model(self):  # pragma: no cover - simple passthrough
        return self.llm, self.sampling_params, "prompt"

    async def get_system_prompt(self, server_rules: str = "") -> str:
        return f"SYSTEM:{server_rules}"

    async def generate_text(self, prompts: list[str]) -> list[str]:
        return [f"resp:{p}" for p in prompts]

    async def unload_model(self) -> None:
        self.state.available = False


@pytest.fixture(autouse=True)
def patch_app_config(monkeypatch):
    fake_app_config = SimpleNamespace(ai_settings=SimpleNamespace(batching={}))
    monkeypatch.setattr("modcord.ai.ai_moderation_processor.app_config", fake_app_config, raising=False)
    yield


@pytest.mark.asyncio
async def test_start_batch_worker_returns_false_when_init_fails(monkeypatch):
    engine = DummyEngine()
    processor = ModerationProcessor(engine=cast(ai_core.InferenceProcessor, engine))
    engine.state.init_started = False

    init_mock = AsyncMock(return_value=False)
    monkeypatch.setattr(processor, "init_model", init_mock)
    monkeypatch.setattr(processor, "_ensure_inference_batch_worker", lambda: None)
    created_tasks: list[asyncio.Task] = []

    def fake_create_task(coro):
        created_tasks.append(coro)
        class _FakeTask:
            def cancel(self):
                pass
            def done(self):
                return True
        return _FakeTask()

    monkeypatch.setattr(asyncio, "create_task", fake_create_task)

    result = await processor.start_batch_worker()

    assert result is False
    init_mock.assert_awaited_once()
    assert created_tasks == []


@pytest.mark.asyncio
async def test_start_batch_worker_schedules_warmup(monkeypatch):
    engine = DummyEngine()
    engine.state.init_started = True
    processor = ModerationProcessor(engine=cast(ai_core.InferenceProcessor, engine))

    ensure_mock = AsyncMock()
    monkeypatch.setattr(processor, "_ensure_inference_batch_worker", ensure_mock)

    scheduled: list[object] = []

    def fake_create_task(coro):
        scheduled.append(coro)
        class _FakeTask:
            def cancel(self):
                pass
            def done(self):
                return False
        return _FakeTask()

    monkeypatch.setattr(asyncio, "create_task", fake_create_task)

    result = await processor.start_batch_worker()

    assert result is True
    ensure_mock.assert_called_once()
    assert len(scheduled) == 1


@pytest.mark.asyncio
async def test_batched_inference_worker_processes_queue(monkeypatch):
    engine = DummyEngine()
    engine.state.init_started = True
    processor = ModerationProcessor(engine=cast(ai_core.InferenceProcessor, engine))
    processor._batch_max_prompts = 2
    processor._batch_max_delay = 0.01

    worker_task = asyncio.create_task(processor._batched_inference_worker())
    processor._inference_worker = worker_task

    try:
        fut1 = asyncio.create_task(processor._enqueue_prompt_for_inference("prompt-1"))
        fut2 = asyncio.create_task(processor._enqueue_prompt_for_inference("prompt-2"))

        result1 = await asyncio.wait_for(fut1, timeout=1)
        result2 = await asyncio.wait_for(fut2, timeout=1)

        assert result1 == "resp:prompt-1"
        assert result2 == "resp:prompt-2"
    finally:
        await processor.shutdown()

    assert processor._inference_worker is None
    assert processor.inference_processor.state.available is False


@pytest.mark.asyncio
async def test_get_appropriate_action_handles_empty(monkeypatch):
    processor = ModerationProcessor(engine=cast(ai_core.InferenceProcessor, DummyEngine()))

    action, reason = await processor.get_appropriate_action([], user_id=1, current_message="  ")

    assert action is ActionType.NULL
    assert reason == "empty history"


@pytest.mark.asyncio
async def test_get_appropriate_action_submits_payload(monkeypatch):
    engine = DummyEngine()
    processor = ModerationProcessor(engine=cast(ai_core.InferenceProcessor, engine))

    async def fake_parse_action(response: str):
        payload = json.loads(response)
        if isinstance(payload, dict) and payload.get("action") == "ban":
            return ActionType.BAN, payload.get("reason", "")
        return ActionType.NULL, "invalid"

    async def fake_submit(messages):
        # second message content is the JSON payload we want to inspect
        return json.dumps({"action": "ban", "reason": "bad"})

    history = [
        ModerationMessage(
            message_id="m1",
            user_id="99",
            username="tester",
            content="hello",
            timestamp="2024-01-01T00:00:00Z",
            guild_id=123,
            channel_id=456,
        )
    ]

    monkeypatch.setattr(processor, "submit_inference", fake_submit)
    monkeypatch.setattr(moderation_parsing, "parse_action", fake_parse_action)

    action, reason = await processor.get_appropriate_action(
        history,
        user_id=99,
        current_message="violation",
        server_rules="Be kind",
        channel_id=456,
        username="tester",
        message_timestamp="2024-01-01T00:00:01Z",
    )

    assert action is ActionType.BAN
    assert reason == "bad"


@pytest.mark.asyncio
async def test_get_appropriate_action_handles_empty_message(monkeypatch):
    processor = ModerationProcessor(engine=cast(ai_core.InferenceProcessor, DummyEngine()))
    history = [
        ModerationMessage(
            message_id="m1",
            user_id="1",
            username="user",
            content="previous",
            timestamp="2024-01-01T00:00:00Z",
            guild_id=1,
            channel_id=1,
        )
    ]

    action, reason = await processor.get_appropriate_action(history, user_id=1, current_message="   ")

    assert action is ActionType.NULL
    assert reason == "empty message"


@pytest.mark.asyncio
async def test_ensure_inference_worker_respects_shutdown():
    processor = ModerationProcessor(engine=cast(ai_core.InferenceProcessor, DummyEngine()))
    processor._shutdown = True

    processor._ensure_inference_batch_worker()

    assert processor._inference_worker is None


@pytest.mark.asyncio
async def test_ensure_inference_worker_reuses_existing_task():
    processor = ModerationProcessor(engine=cast(ai_core.InferenceProcessor, DummyEngine()))

    processor._ensure_inference_batch_worker()
    worker = processor._inference_worker

    assert worker is not None
    processor._ensure_inference_batch_worker()
    assert processor._inference_worker is worker

    await processor.shutdown()


@pytest.mark.asyncio
async def test_batched_inference_worker_sets_exception_on_mismatch(monkeypatch):
    engine = DummyEngine()
    processor = ModerationProcessor(engine=cast(ai_core.InferenceProcessor, engine))
    processor._batch_max_prompts = 2
    processor._batch_max_delay = 0.01

    async def mismatched(prompts):
        return ["only-one"]

    engine.generate_text = mismatched  # type: ignore[assignment]

    worker_task = asyncio.create_task(processor._batched_inference_worker())
    processor._inference_worker = worker_task

    fut1 = asyncio.create_task(processor._enqueue_prompt_for_inference("prompt-a"))
    fut2 = asyncio.create_task(processor._enqueue_prompt_for_inference("prompt-b"))

    with pytest.raises(RuntimeError):
        await fut1
    with pytest.raises(RuntimeError):
        await fut2

    await processor.shutdown()


@pytest.mark.asyncio
async def test_batched_inference_worker_sets_exception_on_generate_error(monkeypatch):
    engine = DummyEngine()
    processor = ModerationProcessor(engine=cast(ai_core.InferenceProcessor, engine))

    async def raise_error(prompts):  # noqa: ANN001
        raise ValueError("fail")

    engine.generate_text = raise_error  # type: ignore[assignment]

    worker_task = asyncio.create_task(processor._batched_inference_worker())
    processor._inference_worker = worker_task

    fut = asyncio.create_task(processor._enqueue_prompt_for_inference("prompt"))

    with pytest.raises(ValueError):
        await fut

    await processor.shutdown()


@pytest.mark.asyncio
async def test_shutdown_drains_queue_and_unloads_model(monkeypatch):
    engine = DummyEngine()
    processor = ModerationProcessor(engine=cast(ai_core.InferenceProcessor, engine))

    worker_task = asyncio.create_task(processor._batched_inference_worker())
    processor._inference_worker = worker_task

    fut = asyncio.create_task(processor._enqueue_prompt_for_inference("prompt"))
    await asyncio.sleep(0)

    await processor.shutdown()

    result = await fut
    assert result == "null: shutting down"
    assert processor._inference_worker is None
    assert engine.state.available is False