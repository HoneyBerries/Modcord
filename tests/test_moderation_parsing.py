import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from modcord.util.moderation_datatypes import ActionType
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

        async def test_parse_batch_actions_handles_code_fence_and_string_durations(self) -> None:
                """Ensure fenced payloads with string durations and invalid values are parsed safely."""
                response = """```json
                {
                    "channel_id": "123",
                    "users": [
                        {
                            "user_id": "u1",
                            "action": "timeout",
                            "reason": "first",
                            "message_ids_to_delete": ["m1"],
                            "timeout_duration": "300",
                            "ban_duration": null
                        },
                        {
                            "user_id": "u1",
                            "action": "warn",
                            "reason": "",
                            "message_ids_to_delete": ["m2"],
                            "timeout_duration": null,
                            "ban_duration": "invalid"
                        },
                        {
                            "user_id": "u2",
                            "action": "null",
                            "reason": "initial",
                            "message_ids_to_delete": ["x"],
                            "timeout_duration": null,
                            "ban_duration": null
                        },
                        {
                            "user_id": "u2",
                            "action": "ban",
                            "reason": "final",
                            "message_ids_to_delete": "ignored",
                            "timeout_duration": "1200",
                            "ban_duration": "3600"
                        }
                    ]
                }
                ```"""

                with patch("modcord.util.moderation_parsing._moderation_validator.validate", return_value=None):
                        actions = await moderation_parsing.parse_batch_actions(response, 123)

                self.assertEqual(len(actions), 2)

                first, second = sorted(actions, key=lambda a: a.user_id)

                self.assertEqual(first.user_id, "u1")
                self.assertEqual(first.action, ActionType.TIMEOUT)
                self.assertEqual(first.reason, "first")
                self.assertEqual(first.message_ids, ["m1", "m2"])
                self.assertEqual(first.timeout_duration, 300)
                self.assertIsNone(first.ban_duration)

                self.assertEqual(second.user_id, "u2")
                self.assertEqual(second.action, ActionType.BAN)
                self.assertEqual(second.reason, "final")
                self.assertEqual(second.message_ids, ["x"])
                self.assertEqual(second.timeout_duration, 1200)
                self.assertEqual(second.ban_duration, 3600)

        async def test_parse_batch_actions_returns_empty_for_non_object_payload(self) -> None:
                """Non-dict top-level payloads should produce an empty result."""
                response = "[1, 2, 3]"

                actions = await moderation_parsing.parse_batch_actions(response, 123)

                self.assertEqual(actions, [])

        async def test_parse_batch_actions_handles_unexpected_exception(self) -> None:
                """Unexpected exceptions during validation should be caught and return an empty list."""
                response = (
                        '{"channel_id":"123","users":[{"user_id":"u1","action":"warn",'
                        '"reason":"test","message_ids_to_delete":["m1"],"timeout_duration":null,'
                        '"ban_duration":null}]}'
                )

                with patch(
                        "modcord.util.moderation_parsing._moderation_validator.validate",
                        side_effect=RuntimeError("boom"),
                ):
                        actions = await moderation_parsing.parse_batch_actions(response, 123)

                self.assertEqual(actions, [])

