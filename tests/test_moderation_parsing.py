import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from modcord.util.moderation_models import ActionType
from modcord.util import moderation_parsing


class ParseActionTests(unittest.IsolatedAsyncioTestCase):
    """Async tests validating the single-action parsing helper."""

    async def test_parse_action_handles_code_fence(self) -> None:
        """Ensure JSON wrapped in code fences is parsed successfully."""
        response = """```json\n{\n  \"action\": \"warn\",\n  \"reason\": \"spam\"\n}\n```"""

        action, reason = await moderation_parsing.parse_action(response)

        self.assertEqual(action, ActionType.WARN)
        self.assertEqual(reason, "spam")

    async def test_parse_action_unknown_action(self) -> None:
        """Unknown action values should degrade to NULL responses."""
        action, reason = await moderation_parsing.parse_action('{"action": "banish", "reason": "nope"}')

        self.assertEqual(action, ActionType.NULL)
        self.assertEqual(reason, "unknown action type")

    async def test_parse_action_invalid_json(self) -> None:
        """Invalid JSON payloads should surface the fallback reason."""
        action, reason = await moderation_parsing.parse_action("not json")

        self.assertEqual(action, ActionType.NULL)
        self.assertEqual(reason, "invalid JSON response")


class ParseBatchActionsTests(unittest.IsolatedAsyncioTestCase):
    """Async tests covering conversion of batch moderation payloads into actions."""

    async def test_parses_message_ids_to_delete(self) -> None:
        """Validate that message IDs are preserved when parsing warn actions."""
        response = (
            '{"channel_id":"123","users":[{"user_id":"u1","action":"warn",'
            '"reason":"test","message_ids_to_delete":["m1"],"timeout_duration":null,'
            '"ban_duration":null}]}'
        )

        actions = await moderation_parsing.parse_batch_actions(response, 123)

        self.assertEqual(len(actions), 1)
        action = actions[0]
        self.assertEqual(action.user_id, "u1")
        self.assertEqual(action.action, ActionType.WARN)
        self.assertEqual(action.reason, "test")
        self.assertEqual(action.message_ids, ["m1"])
        self.assertIsNone(action.timeout_duration)
        self.assertIsNone(action.ban_duration)

    async def test_invalid_schema_returns_empty(self) -> None:
        """Ensure invalid payloads result in an empty list of moderation actions."""
        response = (
            '{"channel_id":"123","users":[{"user_id":"u1","action":"warn"}]}'
        )

        actions = await moderation_parsing.parse_batch_actions(response, 123)

        self.assertEqual(actions, [])

    async def test_channel_mismatch_returns_empty(self) -> None:
        """A mismatch between response channel and expected channel returns no actions."""
        response = (
            '{"channel_id":"999","users":[{"user_id":"u1","action":"warn",'
            '"reason":"test","message_ids_to_delete":[],"timeout_duration":null,'
            '"ban_duration":null}]}'
        )

        actions = await moderation_parsing.parse_batch_actions(response, 123)

        self.assertEqual(actions, [])

    async def test_duplicate_entries_merge_actions(self) -> None:
        """Duplicate user entries should merge message IDs and keep non-null actions."""
        response = (
            '{"channel_id":"123","users":['
            '{"user_id":"u1","action":"null","reason":"initial",'
            '"message_ids_to_delete":["a"],"timeout_duration":null,"ban_duration":null},'
            '{"user_id":"u1","action":"timeout","reason":"second",'
            '"message_ids_to_delete":["b"],"timeout_duration":600,"ban_duration":null}'
            ']}'
        )

        actions = await moderation_parsing.parse_batch_actions(response, 123)

        self.assertEqual(len(actions), 1)
        action = actions[0]
        self.assertEqual(action.action, ActionType.TIMEOUT)
        self.assertEqual(action.reason, "second")
        self.assertCountEqual(action.message_ids, ["a", "b"])
        self.assertEqual(action.timeout_duration, 600)

