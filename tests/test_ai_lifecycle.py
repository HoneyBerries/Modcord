from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest

from modcord.ai.ai_core import ModelState
from modcord.ai.ai_moderation_processor import ModerationProcessor
from modcord.ai.ai_lifecycle import AIEngineLifecycle


@pytest.mark.asyncio
async def test_initialize_invokes_processor_methods():
    state = SimpleNamespace(available=True, init_error=None)
    processor = SimpleNamespace(
        init_model=AsyncMock(return_value=True),
        start_batch_worker=AsyncMock(return_value=True),
        shutdown=AsyncMock(),
    )

    lifecycle = AIEngineLifecycle(
        cast(ModerationProcessor, processor),
        cast(ModelState, state),
    )

    available, detail = await lifecycle.initialize()

    processor.init_model.assert_awaited_once()
    processor.start_batch_worker.assert_awaited_once()
    assert available is True
    assert detail is None


@pytest.mark.asyncio
async def test_restart_resets_state_and_handles_shutdown_error():
    state = SimpleNamespace(available=True, init_error="old error")

    async def fake_init(model=None):
        state.available = True
        state.init_error = None
        return True

    async def fake_start():
        state.available = True
        return True

    processor = SimpleNamespace(
        init_model=AsyncMock(side_effect=fake_init),
    start_batch_worker=AsyncMock(side_effect=fake_start),
        shutdown=AsyncMock(side_effect=RuntimeError("boom")),
    )

    lifecycle = AIEngineLifecycle(
        cast(ModerationProcessor, processor),
        cast(ModelState, state),
    )

    available, detail = await lifecycle.restart(model="gpt")

    processor.shutdown.assert_awaited_once()
    processor.init_model.assert_awaited_once_with("gpt")
    processor.start_batch_worker.assert_awaited_once()
    assert available is True
    assert detail is None


@pytest.mark.asyncio
async def test_shutdown_delegates_to_processor():
    state = SimpleNamespace()
    processor = SimpleNamespace(
        shutdown=AsyncMock(return_value=None),
        init_model=AsyncMock(),
        start_batch_worker=AsyncMock(),
    )

    lifecycle = AIEngineLifecycle(
        cast(ModerationProcessor, processor),
        cast(ModelState, state),
    )

    await lifecycle.shutdown()

    processor.shutdown.assert_awaited_once()
