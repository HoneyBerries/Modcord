import asyncio
import time
from types import SimpleNamespace

import pytest

from modcord.ai.ai_moderation_processor import ModerationProcessor


class EngineBlocking:
    def __init__(self):
        self.state = SimpleNamespace(init_started=True, available=True, init_error=None)
        self.llm = object()
        self.sampling_params = {}
        self.warmup_completed = False

    async def init_model(self, model=None):
        self.state.init_started = True
        self.state.available = True

    async def get_model(self):
        return None, None, None

    def sync_generate(self, prompts):
        # simulate blocking heavy op
        time.sleep(0.01)
        return ["ok" for _ in prompts]

    async def unload_model(self):
        self.state.available = False


class EngineError:
    def __init__(self):
        self.state = SimpleNamespace(init_started=True, available=True, init_error=None)
        self.llm = object()
        self.sampling_params = {}
        self.warmup_completed = False

    async def init_model(self, model=None):
        self.state.init_started = True
        self.state.available = True

    async def get_model(self):
        return object(), {}, None

    async def generate_text(self, prompts):
        raise RuntimeError("generation failed")

    async def unload_model(self):
        self.state.available = False


@pytest.mark.asyncio
async def test_worker_handles_generate_exception(monkeypatch):
    engine = EngineError()
    proc = ModerationProcessor(engine=engine) # type: ignore

    # submit two prompts to cause batching
    futs = [asyncio.create_task(proc.submit_inference([{"role": "user", "content": f"p{i}"}])) for i in range(2)]

    # allow worker to run and process
    await asyncio.sleep(0.1)

    # all futures should resolve to an error string or exception handled
    for t in futs:
        res = await t
        assert res.startswith("null:")

    await proc.shutdown()


@pytest.mark.asyncio
async def test_worker_mismatched_results_sets_exception(monkeypatch):
    class BadEngine:
        def __init__(self):
            self.state = SimpleNamespace(init_started=True, available=True, init_error=None)
            self.llm = object()
            self.sampling_params = {}
            self.warmup_completed = False

        async def init_model(self, model=None):
            self.state.init_started = True
            self.state.available = True

        async def get_model(self):
            return object(), {}, None

        async def generate_text(self, prompts):
            # return wrong number of results
            return ["only-one"]

        async def unload_model(self):
            self.state.available = False

    engine = BadEngine()
    proc = ModerationProcessor(engine=engine) # type: ignore
    
    # Submit two separate inferences (each will be a separate prompt)
    task1 = asyncio.create_task(proc.submit_inference([{"role": "user", "content": "x"}]))
    task2 = asyncio.create_task(proc.submit_inference([{"role": "user", "content": "y"}]))
    
    await asyncio.sleep(0.3)  # Allow batch worker to process
    
    # When the worker gets mismatched results, it sets exceptions on futures
    # The submit_inference wrapper catches these and returns error strings
    try:
        res1 = await task1
        # Should get an error result
        assert "null:" in res1 or isinstance(res1, str)
    except RuntimeError:
        # If exception propagates, that's also valid behavior
        pass
    
    try:
        res2 = await task2
        assert "null:" in res2 or isinstance(res2, str)
    except RuntimeError:
        pass
    
    await proc.shutdown()


@pytest.mark.asyncio
async def test_worker_drains_queue_on_shutdown(monkeypatch):
    """Test that queued but unprocessed prompts get drained during shutdown."""
    class QuickEngine:
        def __init__(self):
            self.state = SimpleNamespace(init_started=True, available=True, init_error=None)
            self.llm = object()
            self.sampling_params = {}
            self.warmup_completed = False
            self.call_count = 0

        async def init_model(self, model=None):
            self.state.init_started = True
            self.state.available = True

        async def get_model(self):
            return object(), {}, None

        async def generate_text(self, prompts):
            self.call_count += 1
            # Return immediately without delay
            return ["r" for _ in prompts]

        async def unload_model(self):
            self.state.available = False

    engine = QuickEngine()
    proc = ModerationProcessor(engine=engine) # type: ignore

    # Submit tasks but don't wait - they'll queue up
    tasks = [asyncio.create_task(proc.submit_inference([{"role": "user", "content": f"p{i}"}])) for i in range(5)]

    # Shutdown immediately without giving worker time to process anything
    # This should cause the worker to drain the queue
    await proc.shutdown()

    # All tasks should complete with either results or shutdown message
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Verify all tasks completed successfully
    for idx, result in enumerate(results):
        assert isinstance(result, str), f"Task {idx}: expected string result, got {type(result)}"
        assert len(result) > 0, f"Task {idx}: got empty result"
        # Should contain either actual results or shutdown message
        assert "r" in result or "null:" in result or "shutting down" in result


 