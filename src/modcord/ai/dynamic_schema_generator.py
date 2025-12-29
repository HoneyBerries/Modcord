from modcord.datatypes.discord_datatypes import UserID, MessageID, ChannelID
from typing import Dict, List

from modcord.util.logger import get_logger


logger = get_logger("dynamic_schema_generator")


def build_dynamic_moderation_schema(
    user_message_map: Dict[UserID, List[MessageID]], 
    channel_id: ChannelID
) -> dict:
    """Build a dynamic JSON schema that requires an action for each specific user.
    
    Constrains AI outputs to valid user IDs, channel ID, and per-user message IDs.
    This prevents hallucination and cross-user deletion since the schema enforces that only the provided message IDs can be referenced.
    
    Args:
        user_message_map: Dict mapping user_id -> list of their message IDs (non-history only)
        channel_id: The channel ID
        
    Returns:
        JSON schema dict with per-user message ID constraints
    """
    if not user_message_map:
        # Fallback for empty batch - no users to moderate
        # Return schema that expects empty users array
        logger.warning("[SCHEMA] Empty user_message_map - no users with valid content to moderate")
        return {
            "type": "object",
            "properties": {
                "channel_id": {"type": "integer", "enum": [channel_id.to_int()]},
                "users": {"type": "array", "maxItems": 0}
            },
            "required": ["channel_id", "users"],
            "additionalProperties": False
        }
    
    
    user_ids = list(user_message_map.keys())
    
    # Build per-user schema with constrained message IDs
    # Use oneOf to enforce different message ID constraints per user
    user_schemas = []
    for user_id, message_ids in user_message_map.items():
        # Handle message_ids_to_delete constraint based on available messages
        if message_ids:
            # User has messages - constrain to their specific message IDs
            message_constraint = {
                "type": "array",
                "items": {"type": "integer", "enum": [mid.to_int() for mid in message_ids]}
            }
        else:
            # User has no messages - must return empty array (no enum constraint)
            message_constraint = {
                "type": "array",
                "items": {"type": "integer"},
                "maxItems": 0  # Force empty array since no messages available
            }
        
        user_schemas.append({
            "type": "object",
            "properties": {
                "user_id": {"type": "integer", "enum": [user_id.to_int()]},
                "action": {"type": "string", "enum": ["null", "delete", "warn", "timeout", "kick", "ban", "review"]},
                "reason": {"type": "string"},
                "message_ids_to_delete": message_constraint,
                "timeout_duration": {"type": "integer", "minimum": 0, "maximum": 60*24*7},  # up to 7 days
                "ban_duration": {"type": "integer", "minimum": -1, "maximum": 60*24*365},  # up to 1 year or permanent
            },
            "required": ["user_id", "action", "reason", "message_ids_to_delete", "timeout_duration", "ban_duration"],
            "additionalProperties": False
        })
    
    return {
        "type": "object",
        "properties": {
            "channel_id": {"type": "integer", "enum": [channel_id.to_int()]},
            "users": {
                "type": "array",
                "items": {"oneOf": user_schemas},
                "minItems": len(user_ids),
                "maxItems": len(user_ids)
            }
        },
        "required": ["channel_id", "users"],
        "additionalProperties": False
    }