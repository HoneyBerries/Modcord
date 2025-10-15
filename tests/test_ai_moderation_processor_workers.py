"""Tests for ModerationProcessor warmup and inference operations.

These tests verify the simplified async architecture where:
- start_batch_worker() performs warmup directly (no background workers)
- submit_inference() calls generate_text() directly (no queueing)
- shutdown() only handles model unloading
"""
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
        self.engine = object()
        self.sampling_params = object()
        self.warmup_completed = False

    async def init_model(self, model: str | None = None) -> bool:
        self.state.init_started = True
        return True

    async def get_model(self):  # pragma: no cover - simple passthrough
        return self.engine, self.sampling_params, "prompt"

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
    """Test that start_batch_worker returns False when model initialization fails."""
    engine = DummyEngine()
    processor = ModerationProcessor(engine=cast(ai_core.InferenceProcessor, engine))
    engine.state.init_started = False

    init_mock = AsyncMock(return_value=False)
    monkeypatch.setattr(processor, "init_model", init_mock)

    result = await processor.start_batch_worker()

    assert result is False
    init_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_batch_worker_schedules_warmup(monkeypatch):
    """Test that start_batch_worker performs warmup when model is initialized."""
    engine = DummyEngine()
    engine.state.init_started = True
    processor = ModerationProcessor(engine=cast(ai_core.InferenceProcessor, engine))

    # Warmup should call generate_text once
    generate_calls = []
    original_generate = engine.generate_text
    async def tracked_generate(prompts):
        generate_calls.append(prompts)
        return await original_generate(prompts)
    
    engine.generate_text = tracked_generate

    result = await processor.start_batch_worker()

    assert result is True
    assert len(generate_calls) == 1  # Warmup call
    assert engine.warmup_completed is True


@pytest.mark.asyncio
async def test_get_appropriate_action_handles_empty(monkeypatch):
    """Test that get_appropriate_action handles empty history correctly."""
    processor = ModerationProcessor(engine=cast(ai_core.InferenceProcessor, DummyEngine()))

    action, reason = await processor.get_appropriate_action([], user_id=1, current_message="  ")

    assert action is ActionType.NULL
    assert reason == "empty history"


@pytest.mark.asyncio
async def test_get_appropriate_action_handles_empty_message(monkeypatch):
    """Test that get_appropriate_action handles empty message correctly."""
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
async def test_shutdown_unloads_model():
    """Test that shutdown properly unloads the model."""
    engine = DummyEngine()
    processor = ModerationProcessor(engine=cast(ai_core.InferenceProcessor, engine))

    await processor.shutdown()

    assert engine.state.available is False
    assert processor._shutdown is True
