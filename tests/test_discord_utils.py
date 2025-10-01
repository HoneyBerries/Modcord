import unittest

from modcord.util.discord_utils import (
    PERMANENT_DURATION,
    build_dm_message,
    format_duration,
    parse_duration_to_seconds,
)
from modcord.util.moderation_models import ActionType


class DiscordUtilsFormattingTests(unittest.TestCase):
    def test_format_duration_handles_special_cases(self) -> None:
        self.assertEqual(format_duration(0), PERMANENT_DURATION)
        self.assertEqual(format_duration(45), "45 secs")
        self.assertEqual(format_duration(120), "2 mins")
        self.assertEqual(format_duration(3600), "1 hour")
        self.assertEqual(format_duration(90000), "1 day")

    def test_parse_duration_to_seconds_known_values(self) -> None:
        self.assertEqual(parse_duration_to_seconds("60 secs"), 60)
        self.assertEqual(parse_duration_to_seconds("1 week"), 7 * 24 * 60 * 60)
        self.assertEqual(parse_duration_to_seconds("Till the end of time"), 0)
        # Unknown labels should fall back to zero seconds
        self.assertEqual(parse_duration_to_seconds("unknown"), 0)


class DiscordUtilsDmMessageTests(unittest.TestCase):
    def test_build_dm_message_for_ban(self) -> None:
        message = build_dm_message(ActionType.BAN, "Guild", "Rule violation", "2 hours")
        self.assertIn("banned from Guild for 2 hours", message)
        self.assertIn("Rule violation", message)

    def test_build_dm_message_for_permanent_ban(self) -> None:
        message = build_dm_message(ActionType.BAN, "Guild", "Rule violation", PERMANENT_DURATION)
        self.assertIn("permanently", message.lower())

    def test_build_dm_message_for_warn(self) -> None:
        message = build_dm_message(ActionType.WARN, "Guild", "Be kind")
        self.assertIn("warning", message.lower())
        self.assertIn("Be kind", message)


if __name__ == "__main__":  # pragma: no cover - direct invocation guard
    unittest.main()
