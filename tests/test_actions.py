import unittest
from modcord.actions import ActionType

class TestActions(unittest.TestCase):
    def test_string_to_action_type(self):
        """Test conversion of string to ActionType enum."""
        self.assertEqual(ActionType("ban"), ActionType.BAN)
        self.assertEqual(ActionType("kick"), ActionType.KICK)
        self.assertEqual(ActionType("warn"), ActionType.WARN)
        self.assertEqual(ActionType("delete"), ActionType.DELETE)
        self.assertEqual(ActionType("null"), ActionType.NULL)

        # Test that an invalid string raises a ValueError
        with self.assertRaises(ValueError):
            ActionType("invalid")

if __name__ == '__main__':
    unittest.main()
