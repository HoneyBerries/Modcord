import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from modcord.util.moderation_models import ActionType
from modcord.util import moderation_parsing


class ParseBatchActionsTests(unittest.IsolatedAsyncioTestCase):
    async def test_parses_message_ids_to_delete(self) -> None:
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

    async def test_fallback_to_legacy_message_ids(self) -> None:
        response = (
            '{"channel_id":"123","users":[{"user_id":"u1","action":"delete",'
            '"reason":"legacy","message_ids":["m2"],"timeout_duration":null,'
            '"ban_duration":null}]}'
        )

        actions = await moderation_parsing.parse_batch_actions(response, 123)

        self.assertEqual(len(actions), 1)
        action = actions[0]
        self.assertEqual(action.user_id, "u1")
        self.assertEqual(action.action, ActionType.DELETE)
        self.assertEqual(action.message_ids, ["m2"])
        self.assertIsNone(action.timeout_duration)
        self.assertIsNone(action.ban_duration)

