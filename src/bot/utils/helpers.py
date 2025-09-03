"""
Helper functions for the bot.
"""
import re
import discord
from ..models.action import ActionType
from ..config.logger import get_logger
from .constants import DURATIONS

logger = get_logger(__name__)

def has_permissions(ctx: discord.ApplicationContext, **perms) -> bool:
    """
    Check if the command issuer has the required permissions.
    """
    if not isinstance(ctx.author, discord.Member):
        return False
    return all(getattr(ctx.author.guild_permissions, perm, False) for perm in perms)


def parse_duration_to_seconds(duration_str: str) -> int:
    """
    Convert a human-readable duration string to its equivalent in seconds.
    """
    return DURATIONS.get(duration_str, 0)


async def send_dm_to_user(user: discord.Member, message: str) -> bool:
    """
    Attempt to send a direct message to a user.
    """
    try:
        await user.send(message)
        return True
    except discord.Forbidden:
        logger.info(f"Could not DM {user.display_name}: They may have DMs disabled.")
    except Exception as e:
        logger.error(f"Failed to send DM to {user.display_name}: {e}")
    return False

def parse_action(assistant_response: str) -> tuple[ActionType, str]:
    """
    Parses the AI model's response to extract the moderation action and reason.
    """
    action_pattern = r"^(delete|warn|timeout|kick|ban|null)\s*:\s*(.+)$"
    match = re.match(action_pattern, assistant_response.strip(), re.IGNORECASE | re.DOTALL)

    if match:
        action_str, reason = match.groups()
        action_str = action_str.strip().lower()
        reason = reason.strip()

        try:
            action = ActionType(action_str)
        except ValueError:
            logger.warning(f"Unknown action type: '{action_str}'")
            return ActionType.NULL, "unknown action type"

        action_prefixes = [at.value for at in ActionType]
        for prefix in action_prefixes:
            if reason.lower().startswith(f"{prefix}:"):
                reason = reason[len(prefix)+1:].strip()
                break

        if action == ActionType.NULL:
            return ActionType.NULL, "no action needed"
        else:
            return action, reason

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
            logger.warning(f"Unknown action type: '{action_str}'")
            return ActionType.NULL, "unknown action type"

    logger.warning(f"Invalid response format: '{assistant_response}'")
    return ActionType.NULL, "invalid AI response format"
