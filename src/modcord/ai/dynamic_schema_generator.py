from modcord.datatypes.discord_datatypes import UserID, MessageID, GuildID
from typing import Dict, List

from modcord.util.logger import get_logger


logger = get_logger("dynamic_schema_generator")


def build_server_moderation_schema(
    user_message_map: Dict[UserID, List[MessageID]],
    guild_id: GuildID,
) -> dict:
    """Build a dynamic JSON schema for server-wide moderation.

    Constrains AI outputs to valid user IDs and per-user message IDs across
    all channels in the guild.  There is no channel_id constraint — the AI
    operates at the server level and channel context is provided in the
    JSON payload instead.

    Args:
        user_message_map: Dict mapping user_id -> list of their message IDs (non-history only,
                          across all channels in the batch).
        guild_id: The guild (server) ID.

    Returns:
        JSON schema dict with per-user message ID constraints.
    """
    if not user_message_map:
        logger.warning("[SCHEMA] Empty user_message_map - no users with valid content to moderate")
        return {
            "type": "object",
            "properties": {
                "guild_id": {"type": "integer", "enum": [guild_id.to_int()]},
                "users": {"type": "array", "maxItems": 0}
            },
            "required": ["guild_id", "users"],
            "additionalProperties": False
        }

    user_ids = list(user_message_map.keys())

    # Build per-user schema with constrained message IDs
    user_schemas = []
    for user_id, message_ids in user_message_map.items():
        if message_ids:
            message_constraint = {
                "type": "array",
                "items": {"type": "integer", "enum": [mid.to_int() for mid in message_ids]}
            }
        else:
            message_constraint = {
                "type": "array",
                "items": {"type": "integer"},
                "maxItems": 0
            }

        user_schemas.append({
            "type": "object",
            "properties": {
                "user_id": {"type": "integer", "enum": [user_id.to_int()]},
                "action": {"type": "string", "enum": ["null", "delete", "warn", "timeout", "kick", "ban", "review"]},
                "reason": {"type": "string"},
                "message_ids_to_delete": message_constraint,
                "timeout_duration": {"type": "integer", "minimum": 0, "maximum": 60 * 24 * 7},
                "ban_duration": {"type": "integer", "minimum": -1, "maximum": 60 * 24 * 365},
            },
            "required": ["user_id", "action", "reason", "message_ids_to_delete", "timeout_duration", "ban_duration"],
            "additionalProperties": False
        })

    return {
        "type": "object",
        "properties": {
            "guild_id": {"type": "integer", "enum": [guild_id.to_int()]},
            "users": {
                "type": "array",
                "items": {"oneOf": user_schemas},
                "minItems": len(user_ids),
                "maxItems": len(user_ids)
            }
        },
        "required": ["guild_id", "users"],
        "additionalProperties": False
    }