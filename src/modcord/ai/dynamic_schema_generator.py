from typing import Dict, List, Set

from modcord.datatypes.discord_datatypes import ChannelID, UserID, MessageID
from modcord.datatypes.moderation_datatypes import ServerModerationBatch
from modcord.util.logger import get_logger

logger = get_logger("dynamic_schema_generator")


def build_server_moderation_schema(
    batch: ServerModerationBatch,
) -> dict:
    """Build a dynamic JSON schema for server-wide moderation.

    Constrains AI outputs to valid user IDs and, for each user, valid
    channel IDs with per-channel message IDs.

    Expected AI response shape::

        {
          "guild_id": "<string>",
          "users": [
            {
              "user_id": "<string>",
              "action": "null|delete|warn|timeout|kick|ban",
              "reason": "<string>",
              "channels": [
                {
                  "channel_id": "<string>",
                  "message_ids_to_delete": ["<mid>", ...]
                }
              ],
              "timeout_duration": <int>,
              "ban_duration": <int>
            }
          ]
        }

    Only the non-history users in the batch are eligible for moderation
    actions; history users provide context only and are excluded from the
    schema (but their message IDs are added to the allowed-deletion set).

    All snowflake fields are ``"type": "string"`` to prevent IEEE 754
    precision loss on 64-bit Discord snowflakes.

    Args:
        batch: ServerModerationBatch with current and history users.

    Returns:
        JSON schema dict with per-user, per-channel message ID constraints.
    """
    guild_id = batch.guild_id

    if not batch.users:
        logger.warning("[SCHEMA] Empty batch.users — no users to moderate")
        return {
            "type": "object",
            "properties": {
                "guild_id": {"type": "string", "enum": [str(guild_id)]},
                "users": {"type": "array", "maxItems": 0},
            },
            "required": ["guild_id", "users"],
            "additionalProperties": False,
        }

    # ---- collect user → channel → message-id sets -------------------
    # Start with current (non-history) users
    user_channel_msgs: Dict[UserID, Dict[ChannelID, Set[MessageID]]] = {}
    user_channel_names: Dict[UserID, Dict[ChannelID, str]] = {}

    for user in batch.users:
        ch_map: Dict[ChannelID, Set[MessageID]] = {}
        ch_names: Dict[ChannelID, str] = {}
        for uch in user.channels:
            ch_map[uch.channel_id] = {msg.message_id for msg in uch.messages}
            ch_names[uch.channel_id] = uch.channel_name
        user_channel_msgs[user.user_id] = ch_map
        user_channel_names[user.user_id] = ch_names

    # Merge history message IDs into existing users' channels
    for history_user in batch.history_users:
        if history_user.user_id not in user_channel_msgs:
            continue  # history-only user — not moderated
        ch_map = user_channel_msgs[history_user.user_id]
        ch_names = user_channel_names[history_user.user_id]
        for uch in history_user.channels:
            ch_map.setdefault(uch.channel_id, set())
            ch_names.setdefault(uch.channel_id, uch.channel_name)
            for msg in uch.messages:
                ch_map[uch.channel_id].add(msg.message_id)

    # ---- build JSON schema ------------------------------------------
    user_schemas: List[dict] = []
    for user_id, ch_map in user_channel_msgs.items():
        ch_names = user_channel_names[user_id]

        channel_schemas: List[dict] = []
        for ch_id, msg_ids_set in ch_map.items():
            sorted_mids: List[str] = sorted(str(mid) for mid in msg_ids_set)

            if sorted_mids:
                mid_constraint = {
                    "type": "array",
                    "items": {"type": "string", "enum": sorted_mids},
                }
            else:
                mid_constraint = {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 0,
                }

            channel_schemas.append({
                "type": "object",
                "properties": {
                    "channel_id": {"type": "string", "enum": [str(ch_id)]},
                    "message_ids_to_delete": mid_constraint,
                },
                "required": ["channel_id", "message_ids_to_delete"],
                "additionalProperties": False,
            })

        # channels array for this user — oneOf per channel
        if channel_schemas:
            channels_constraint: dict = {
                "type": "array",
                "items": {"oneOf": channel_schemas},
                "minItems": len(channel_schemas),
                "maxItems": len(channel_schemas),
            }
        else:
            channels_constraint = {
                "type": "array",
                "maxItems": 0,
            }

        user_schemas.append({
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "enum": [str(user_id)]},
                "action": {
                    "type": "string",
                    "enum": ["null", "delete", "warn", "timeout", "kick", "ban"],
                },
                "reason": {"type": "string"},
                "channels": channels_constraint,
                "timeout_duration": {"type": "integer", "minimum": 0, "maximum": 60 * 24 * 7},
                "ban_duration": {"type": "integer", "minimum": -1, "maximum": 60 * 24 * 365},
            },
            "required": ["user_id", "action", "reason", "channels", "timeout_duration", "ban_duration"],
            "additionalProperties": False,
        })

    return {
        "type": "object",
        "properties": {
            "guild_id": {"type": "string", "enum": [str(guild_id)]},
            "users": {
                "type": "array",
                "items": {"oneOf": user_schemas},
                "minItems": len(user_schemas),
                "maxItems": len(user_schemas),
            },
        },
        "required": ["guild_id", "users"],
        "additionalProperties": False,
    }