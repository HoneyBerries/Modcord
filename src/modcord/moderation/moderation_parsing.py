"""Utilities for parsing AI moderation responses with dynamic schema generation."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List
from jsonschema import ValidationError

from modcord.moderation.moderation_datatypes import ActionData, ActionType
import jsonschema

logger = logging.getLogger("moderation_parsing")


def build_dynamic_moderation_schema(
    user_message_map: Dict[str, List[str]], 
    channel_id: str
) -> dict:
    """Build a dynamic JSON schema that requires an action for each specific user.
    
    Constrains AI outputs to valid user IDs, channel ID, and per-user message IDs.
    This prevents hallucination and cross-user deletion since xgrammar enforces 
    the schema at generation time.
    
    Args:
        user_message_map: Dict mapping user_id -> list of their message IDs (non-history only)
        channel_id: The channel ID string
        
    Returns:
        JSON schema dict with per-user message ID constraints
    """
    if not user_message_map:
        # Fallback for empty batch (shouldn't happen in practice)
        return {
            "type": "object",
            "properties": {
                "channel_id": {"type": "string", "enum": [channel_id]},
                "users": {"type": "array", "items": {}, "minItems": 0, "maxItems": 0}
            },
            "required": ["channel_id", "users"],
            "additionalProperties": False
        }
    
    user_ids = list(user_message_map.keys())
    
    # Build per-user schema with constrained message IDs
    # Use oneOf to enforce different message ID constraints per user
    user_schemas = []
    for user_id, message_ids in user_message_map.items():
        user_schemas.append({
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "enum": [user_id]},
                "action": {"type": "string", "enum": ["null", "delete", "warn", "timeout", "kick", "ban"]},
                "reason": {"type": "string"},
                "message_ids_to_delete": {
                    "type": "array",
                    "items": {"type": "string", "enum": message_ids if message_ids else []}
                },
                "timeout_duration": {"type": "integer", "minimum": 0},
                "ban_duration": {"type": "integer", "minimum": -1},
            },
            "required": ["user_id", "action", "reason", "message_ids_to_delete", "timeout_duration", "ban_duration"],
            "additionalProperties": False
        })
    
    return {
        "type": "object",
        "properties": {
            "channel_id": {"type": "string", "enum": [channel_id]},
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


def _extract_json_payload(raw: str) -> Any:
    """Extract JSON object from raw text using json.loads()."""
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError as exc:
        raise ValueError("Unable to decode JSON payload") from exc


def parse_batch_actions(
    response: str,
    channel_id: int,
    expected_schema: dict
) -> List[ActionData]:
    """Parse AI moderation response into ActionData objects.
    
    Assumes response is valid according to the schema (enforced by xgrammar at generation).
    Performs only JSON extraction and basic parsing - no reconciliation.
    
    Args:
        response: Model response text containing JSON
        channel_id: Expected channel identifier
        expected_schema: JSON schema used for validation
        
    Returns:
        List of ActionData objects parsed from response
    """
    logger.debug("[PARSE] Parsing batch response (%d chars)", len(response))
    
    # Extract JSON
    try:
        payload = _extract_json_payload(response)
    except ValueError as exc:
        logger.error("[PARSE] Failed to extract JSON: %s", exc)
        return []
    
    if not isinstance(payload, dict):
        logger.error("[PARSE] Payload is not a dict, got %s", type(payload))
        return []
    
    # Validate against schema (should pass due to xgrammar constraint)
    try:
        jsonschema.validate(instance=payload, schema=expected_schema)
    except ValidationError as exc:
        logger.error("[PARSE] Schema validation failed: %s", exc.message)
        return []
    
    # Verify channel ID matches
    response_channel = str(payload.get("channel_id", "")).strip()
    if response_channel != str(channel_id):
        logger.warning("[PARSE] Channel mismatch: expected %s, got %s", channel_id, response_channel)
        return []
    
    entries = payload.get("users") or []
    if not isinstance(entries, list):
        logger.error("[PARSE] 'users' field is not a list")
        return []
    
    logger.debug("[PARSE] Extracted %d user entries", len(entries))
    
    # Parse each action - trust schema, just normalize data
    actions: List[ActionData] = []
    
    for item in entries:
        if not isinstance(item, dict):
            continue
        
        user_id = str(item.get("user_id", "")).strip()
        action_str = str(item.get("action", "null")).lower()
                
        # Extract message IDs
        raw_msg_ids = item.get("message_ids_to_delete") or []
        message_ids = [str(mid).strip() for mid in raw_msg_ids if mid] if isinstance(raw_msg_ids, list) else []
        
        # Extract durations (may be None or -1)
        try:
            timeout_dur = int(item["timeout_duration"]) if item.get("timeout_duration") not in (None, "") else None
        except (ValueError, TypeError):
            timeout_dur = None
        
        try:
            ban_dur = int(item["ban_duration"]) if item.get("ban_duration") not in (None, "") else None
        except (ValueError, TypeError):
            ban_dur = None
        
        # Extract reason
        reason = str(item.get("reason", "")).strip()

        # Create action
        action_type = ActionType(action_str)
        actions.append(
            ActionData(
                user_id=user_id,
                action=action_type,
                reason=reason,
                message_ids=message_ids,
                timeout_duration=timeout_dur,
                ban_duration=ban_dur,
            )
        )
    
    logger.debug("[PARSE] Successfully parsed %d actions", len(actions))
    return actions


