import unittest
import re
from enum import Enum

class ActionType(Enum):
    BAN = "ban"
    UNBAN = "unban"
    KICK = "kick"
    MUTE = "mute"
    WARN = "warn"
    DELETE = "delete"
    TIMEOUT = "timeout"
    NULL = "null"

    def __str__(self):
        return self.value

def parse_action(assistant_response: str) -> tuple[ActionType, str]:
    """
    Parses the AI model's response to extract the moderation action and reason.
    Supports actions: delete, warn, timeout, kick, ban, null.

    Args:
        assistant_response (str): The raw response from the AI model.

    Returns:
        tuple[ActionType, str]: Action type and reason string.
    """
    action_pattern = r"^(delete|warn|timeout|kick|ban|null)\s*[:\s]+(.+)$"
    match = re.match(action_pattern, assistant_response.strip(), re.IGNORECASE | re.DOTALL)

    if match:
        action_str, reason = match.groups()
        action_str = action_str.strip().lower()
        reason = reason.strip()

        # Convert string to ActionType enum
        try:
            action = ActionType(action_str)
        except ValueError:
            return ActionType.NULL, "unknown action type"

        # Fix: Remove redundant <action>: prefix from reason if present
        action_prefixes = [at.value for at in ActionType]
        for prefix in action_prefixes:
            if reason.lower().startswith(f"{prefix}:"):
                reason = reason[len(prefix)+1:].strip()
                break

        # Accept 'null: no action needed' as a valid no-action response
        if action == ActionType.NULL:
            return ActionType.NULL, "no action needed"
        else:
            # Return the valid action and reason without modification
            return action, reason

    # Fallback: Try to extract just the action if parsing failed
    simple_pattern = r"^(delete|warn|timeout|kick|ban|null)$"
    simple_match = re.match(simple_pattern, assistant_response.strip(), re.IGNORECASE)
    if simple_match:
        action_str = simple_match.group(1).lower()
        try:
            action = ActionType(action_str)
            if action == ActionType.NULL:
                return ActionType.NULL, "no action needed"
            return action, "AI response incomplete"
        except ValueError:
            return ActionType.NULL, "unknown action type"

    return ActionType.NULL, "invalid AI response format"

class TestParser(unittest.TestCase):
    def test_parse_action(self):
        # Test ban action
        action, reason = parse_action("ban: User was spamming")
        self.assertEqual(action, ActionType.BAN)
        self.assertEqual(reason, "User was spamming")

        # Test warn action
        action, reason = parse_action("warn: User was being rude")
        self.assertEqual(action, ActionType.WARN)
        self.assertEqual(reason, "User was being rude")

        # Test null action
        action, reason = parse_action("null: No action needed")
        self.assertEqual(action, ActionType.NULL)
        self.assertEqual(reason, "no action needed")

        # Test invalid action
        action, reason = parse_action("invalid: This is not a valid action")
        self.assertEqual(action, ActionType.NULL)
        self.assertEqual(reason, "invalid AI response format")

if __name__ == "__main__":
    unittest.main()
