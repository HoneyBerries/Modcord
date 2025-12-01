from datetime import datetime, timezone
from typing import List

from modcord.util.logger import get_logger
from modcord.datatypes.action_datatypes import ActionData, ActionType

logger = get_logger("format_utils")

def humanize_timestamp(value: datetime) -> str:
    """Return a human-readable timestamp (YYYY-MM-DD HH:MM:SS) in UTC.
    
    Ensures timestamps are never in the future by clamping to current time.

    Args:
        value: datetime object to format.

    Returns:
        Human-readable UTC timestamp string.
    """
    
    # Convert to UTC if it has a different timezone
    if value.tzinfo is not None and value.tzinfo.utcoffset(value) != timezone.utc.utcoffset(None):
        value = value.astimezone(timezone.utc)
    elif value.tzinfo is None:
        # If naive, assume UTC
        value = value.replace(tzinfo=timezone.utc)
    
    # Clamp to current time if timestamp is in the future
    now_utc = datetime.now(timezone.utc)
    if value > now_utc:
        logger.warning(
            "Timestamp %s is in the future, clamping to current time %s",
            value.isoformat(),
            now_utc.isoformat()
        )
        value = now_utc
    
    return value.strftime("%Y-%m-%d %H:%M:%S UTC")


def format_past_actions(past_actions: List[ActionData]) -> List[dict]:
    """Format past moderation actions for inclusion in AI model payload.
    
    Args:
        past_actions: List of ActionData objects from database.
    
    Returns:
        Formatted actions with keys: action, reason, duration (optional).
    """
    formatted_past_actions = []
    for action in past_actions:
        formatted_action = {
            "action": action.action.value,
            "reason": action.reason,
        }
        
        # Include duration for timeout actions
        if action.timeout_duration:
            if action.timeout_duration == -1:
                formatted_action["duration"] = "permanent"
            else:
                formatted_action["duration"] = f"{action.timeout_duration} minutes"
        
        # Include duration for ban actions
        elif action.action == ActionType.BAN:
            if action.ban_duration in (-1, 0):
                formatted_action["duration"] = "permanent"
            elif action.ban_duration:
                formatted_action["duration"] = f"{action.ban_duration} minutes"
        
        formatted_past_actions.append(formatted_action)
    
    return formatted_past_actions