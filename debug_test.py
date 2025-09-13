#!/usr/bin/env python3

import sys
sys.path.append('.')

# Test parse_action directly
import re
from src.modcord.actions import ActionType

def parse_action_test(assistant_response: str) -> tuple:
    """Test version of parse_action to debug the issue"""
    
    # Pattern 2: Check for simple "<action>: <reason>" format (e.g., "ban: User was spamming")
    simple_action_pattern = r'^(delete|warn|timeout|kick|ban|null):\s*(.+)'
    simple_match = re.match(simple_action_pattern, assistant_response.strip(), re.IGNORECASE)
    if simple_match:
        action_str = simple_match.group(1).strip().lower()
        reason = simple_match.group(2).strip()
        
        try:
            action = ActionType(action_str)
            if getattr(action, 'value', str(action)) == 'null':
                return ActionType('null'), "no action needed"
            return action, reason
        except Exception as e:
            print(f"Error creating ActionType for '{action_str}': {e}")
            return ActionType('null'), "unknown action type"
    
    return ActionType('null'), "invalid AI response format"


print("Testing parse_action function...")

# Test the inputs from the failing test
test_cases = [
    "ban: User was spamming",
    "warn: User was being rude", 
    "null: No action needed",
    "kick: User was being disruptive."
]

for test_input in test_cases:
    try:
        action, reason = parse_action_test(test_input)
        print(f"Input: '{test_input}' -> Action: {action}, Reason: '{reason}'")
    except Exception as e:
        print(f"Error parsing '{test_input}': {e}")

# Now test with the actual function
print("\nTesting with actual parse_action function...")
from src.modcord.ai_model import parse_action

for test_input in test_cases:
    try:
        action, reason = parse_action(test_input)
        print(f"Input: '{test_input}' -> Action: {action}, Reason: '{reason}'")
    except Exception as e:
        print(f"Error parsing '{test_input}': {e}")
