import asyncio
import json
from types import SimpleNamespace

import pytest

from modcord.ai.ai_moderation_processor import ModerationProcessor
from modcord.util.moderation_datatypes import ModerationMessage, ActionType
import modcord.util.moderation_parsing as moderation_parsing


class FakeEngine:
    def __init__(self):
        self.state = SimpleNamespace(init_started=True, available=True, init_error=None)
        self.llm = object()
        self.sampling_params = {}
        self.warmup_completed = False

    async def init_model(self, model=None):
        self.state.init_started = True
        self.state.available = True

    async def get_model(self):
        # return a dummy model wrapper, sampling params and extra
        return object(), {"sampling": True}, None

    async def get_system_prompt(self, rules: str):
        return "SYSTEM_PROMPT"

    async def generate_text(self, prompts):
        # return simple echo responses
        return [f"RESPONSE:{p}" for p in prompts]

    async def unload_model(self):
        self.state.available = False


def make_processor(engine=None):
    return ModerationProcessor(engine=engine or FakeEngine()) # type: ignore


def test_messages_to_prompt_formats_roles():
    proc = make_processor()
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "assistant", "content": "assist"},
        {"role": "user", "content": "hello"},
    ]
    prompt = proc.messages_to_prompt(messages)
    assert "[SYSTEM]" in prompt
    assert "[ASSISTANT]" in prompt
    assert "[USER]" in prompt


@pytest.mark.asyncio
async def test_submit_inference_shutdown_short_circuits():
    proc = make_processor()
    proc._shutdown = True
    resp = await proc.submit_inference([{"role": "user", "content": "x"}])
    assert "shutting down" in resp


@pytest.mark.asyncio
async def test_submit_inference_model_unavailable_short_circuits():
    engine = FakeEngine()
    engine.state.init_started = True
    engine.state.available = False
    engine.state.init_error = "offline"
    proc = make_processor(engine=engine)

    resp = await proc.submit_inference([{"role": "user", "content": "x"}])
    assert "offline" in resp


@pytest.mark.asyncio
async def test_submit_inference_success_returns_generated(monkeypatch):
    engine = FakeEngine()
    proc = make_processor(engine=engine)

    # Ensure the worker is created and generate_text path is used
    result = await proc.submit_inference([{"role": "user", "content": "ping"}])
    # generate_text returns RESPONSE:<prompt>, expect non-null
    assert result.startswith("RESPONSE:") or result.startswith("null:") is False


@pytest.mark.asyncio
async def test_get_appropriate_action_uses_parser(monkeypatch):
    engine = FakeEngine()
    proc = make_processor(engine=engine)

    # stub submit_inference to return a simple assistant response
    async def fake_submit(messages):
        # craft an assistant response that parse_action understands
        return json.dumps({"action": "delete", "reason": "test"})

    monkeypatch.setattr(proc, "submit_inference", fake_submit)
    async def fake_parse_action(text):
        return ActionType.DELETE, "test"

    monkeypatch.setattr(moderation_parsing, "parse_action", fake_parse_action)

    history = []
    action, reason = await proc.get_appropriate_action(history, user_id=123, current_message="bad stuff")
    assert action == ActionType.DELETE
    assert reason == "test"
