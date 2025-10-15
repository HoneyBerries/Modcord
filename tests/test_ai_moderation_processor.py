import json
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"


def _ensure_stubbed_dependencies() -> None:
    """Stub minimal dependencies needed for importing AI modules during testing."""
    # Simple stub class that accepts any initialization and method calls
    class _StubClass:
        def __init__(self, *_, **__):
            pass
        def __call__(self, *_, **__):
            return self
        def __getattr__(self, name):
            return _StubClass()
    
    # Stub torch module
    if "torch" not in sys.modules:
        torch_stub = types.ModuleType("torch")
        torch_stub.cuda = _StubClass()
        torch_stub.compile = lambda model, *_, **__: model
        sys.modules["torch"] = torch_stub

    # Stub vllm modules
    if "vllm" not in sys.modules:
        vllm_stub = types.ModuleType("vllm")
        vllm_stub.LLM = _StubClass
        vllm_stub.SamplingParams = _StubClass
        sys.modules["vllm"] = vllm_stub

    if "vllm.sampling_params" not in sys.modules:
        sampling_stub = types.ModuleType("vllm.sampling_params")
        sampling_stub.GuidedDecodingParams = _StubClass
        sys.modules["vllm.sampling_params"] = sampling_stub


_ensure_stubbed_dependencies()

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from modcord.ai.ai_moderation_processor import ModerationProcessor  # type: ignore[import]
from modcord.util.moderation_datatypes import ActionType, ModerationBatch, ModerationMessage  # type: ignore[import]


class ModerationProcessorBatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_consolidates_actions_per_user(self) -> None:
        processor = ModerationProcessor(None)
        processor.inference_processor = SimpleNamespace(
            get_system_prompt=AsyncMock(return_value="prompt"),
        )

        processor.submit_inference = AsyncMock(
            return_value=(
                '{"channel_id":"1","users":['
                '{"user_id":"100","action":"warn","reason":"first","message_ids_to_delete":["ai_msg"],'
                '"timeout_duration":null,"ban_duration":null},'
                '{"user_id":"100","action":"null","reason":"ignore","message_ids_to_delete":["ai_msg2"],'
                '"timeout_duration":null,"ban_duration":null},'
                '{"user_id":"200","action":"delete","reason":"cleanup",'
                '"message_ids_to_delete":[],"timeout_duration":null,"ban_duration":null}'
                ']}'
            )
        )

        batch = ModerationBatch(
            channel_id=1,
            messages=[
                ModerationMessage(
                    message_id="m1",
                    user_id="100",
                    username="user100",
                    content="hi",
                    timestamp="2025-09-27T17:00:00Z",
                    guild_id=None,
                    channel_id=1,
                ),
                ModerationMessage(
                    message_id="m2",
                    user_id="100",
                    username="user100",
                    content="spam",
                    timestamp="2025-09-27T17:00:01Z",
                    guild_id=None,
                    channel_id=1,
                ),
                ModerationMessage(
                    message_id="m3",
                    user_id="200",
                    username="user200",
                    content="bad",
                    timestamp="2025-09-27T17:00:02Z",
                    guild_id=None,
                    channel_id=1,
                ),
            ],
        )

        actions = await processor.get_batch_moderation_actions(batch)

        awaited_call = processor.submit_inference.await_args_list[0]
        sent_messages = awaited_call.args[0]
        self.assertEqual(len(sent_messages), 2)
        payload_str = sent_messages[1]["content"]
        payload = json.loads(payload_str)

        self.assertEqual(payload["channel_id"], "1")
        self.assertEqual(payload["message_count"], 3)
        self.assertEqual(payload["unique_user_count"], 2)
        self.assertEqual(payload["window_start"], "2025-09-27T17:00:00Z")
        self.assertEqual(payload["window_end"], "2025-09-27T17:00:02Z")
        self.assertIn("users", payload)
        self.assertEqual(len(payload["users"]), 2)
        self.assertEqual(
            [msg["role"] for msg in payload["messages"]],
            ["user", "user", "user"],
        )

        users_by_id = {user["user_id"]: user for user in payload["users"]}
        self.assertIn("100", users_by_id)
        self.assertIn("200", users_by_id)
        self.assertEqual(users_by_id["100"]["message_count"], 2)
        self.assertEqual(users_by_id["200"]["message_count"], 1)
        self.assertEqual(
            [msg["message_id"] for msg in users_by_id["100"]["messages"]],
            ["m1", "m2"],
        )
        self.assertEqual(
            [msg["message_id"] for msg in users_by_id["200"]["messages"]],
            ["m3"],
        )

        self.assertEqual(len(actions), 2)

        actions_by_user = {action.user_id: action for action in actions}
        self.assertIn("100", actions_by_user)
        self.assertIn("200", actions_by_user)

        user100 = actions_by_user["100"]
        self.assertEqual(user100.action, ActionType.WARN)
        self.assertEqual(user100.reason, "first")
        self.assertCountEqual(user100.message_ids, ["m1", "m2"])

        user200 = actions_by_user["200"]
        self.assertEqual(user200.action, ActionType.DELETE)
        self.assertEqual(user200.reason, "cleanup")
        self.assertCountEqual(user200.message_ids, ["m3"])
        self.assertIsNone(user200.timeout_duration)
        self.assertIsNone(user200.ban_duration)
