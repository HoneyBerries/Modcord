from modcord.datatypes.discord_datatypes import UserID, MessageID
from modcord.datatypes.moderation_datatypes import ServerModerationBatch
from typing import Dict, List

from modcord.util.logger import get_logger


logger = get_logger("dynamic_schema_generator")


def build_server_moderation_schema(
    batch: ServerModerationBatch,
) -> dict:
    """Build a dynamic JSON schema for server-wide moderation.

    Constrains AI outputs to valid user IDs and per-user message IDs across
    all channels in the guild.  There is no channel_id constraint — the AI
    operates at the server level and channel context is provided in the
    JSON payload instead.

    Only the non-history users in the batch are eligible for moderation actions;
    history users are context only and are excluded from the schema.

    All snowflake ID fields (guild_id, user_id, message_ids_to_delete) are
    declared as "type": "string" in the schema. This prevents IEEE 754 double
    precision loss: 64-bit Discord snowflakes exceed the 53-bit mantissa of
    JSON numbers, causing silent rounding when the LLM emits them as bare
    integer literals. Quoting them as strings bypasses this entirely.
    The parser already normalises all ID fields via str() / DiscordSnowflake,
    so no parser changes are required.

    Args:
        batch: The ServerModerationBatch containing current users and their messages.

    Returns:
        JSON schema dict with per-user message ID constraints.
    """
    guild_id = batch.guild_id

    if not batch.users:
        logger.warning("[SCHEMA] Empty batch.users - no users with valid content to moderate")
        return {
            "type": "object",
            "properties": {
                "guild_id": {"type": "string", "enum": [str(guild_id)]},
                "users": {"type": "array", "maxItems": 0}
            },
            "required": ["guild_id", "users"],
            "additionalProperties": False
        }

    # Build user_id -> message_ids mapping from the batch's current (non-history) users
    user_message_map: Dict[UserID, List[MessageID]] = {
        user.user_id: [msg.message_id for msg in user.messages]
        for user in batch.users
    }

    user_ids = list(user_message_map.keys())

    # Build per-user schema with constrained message IDs.
    # All snowflake fields are "type": "string" to avoid IEEE 754 precision loss.
    user_schemas = []
    for user_id, message_ids in user_message_map.items():
        if message_ids:
            message_constraint = {
                "type": "array",
                "items": {"type": "string", "enum": [str(mid) for mid in message_ids]}
            }
        else:
            message_constraint = {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 0
            }

        user_schemas.append({
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "enum": [str(user_id)]},
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
            "guild_id": {"type": "string", "enum": [str(guild_id)]},
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