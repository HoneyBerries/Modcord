"""Utilities for parsing AI moderation responses with dynamic schema generation."""

from __future__ import annotations

import json
from typing import Any, Dict, List
from jsonschema import ValidationError
from modcord.datatypes.action_datatypes import ActionData, ActionType
from modcord.datatypes.discord_datatypes import ChannelID, UserID, GuildID, MessageID
import jsonschema
from modcord.util.logger import get_logger

logger = get_logger("moderation_parsing")


def _extract_json_payload(raw: str) -> Any:
    """Extract JSON object from raw text using json.loads()."""
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError as exc:
        logger.warning("[EXTRACT] Parsing failed: %s", exc)
        raise ValueError("Failed to extract JSON payload") from exc


def parse_batch_actions(
    response: str,
    channel_id: ChannelID,
    guild_id: GuildID,
    expected_schema: dict
) -> List[ActionData]:
    """Parse AI moderation response into ActionData objects.
    
    Assumes response is valid according to the schema.
    Performs only JSON extraction and basic parsing - no reconciliation.
    
    Args:
        response: Model response text containing JSON
        channel_id: Expected channel identifier
        guild_id: Guild ID to include in ActionData
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
        if type(item) is not dict:
            continue
        
        user_id = str(item.get("user_id", "")).strip()
        action_str = str(item.get("action", "null")).lower()
                
        # Extract message IDs
        raw_msg_ids = item.get("message_ids_to_delete") or []
        message_ids = [MessageID(mid) for mid in raw_msg_ids if mid] if isinstance(raw_msg_ids, list) else []
        
        # Extract durations (may be 0 or -1)
        try:
            timeout_dur = int(item["timeout_duration"]) if item.get("timeout_duration") not in (None, "") else 0
        except (ValueError, TypeError):
            timeout_dur = 0
        
        try:
            ban_dur = int(item["ban_duration"]) if item.get("ban_duration") not in (None, "") else 0
        except (ValueError, TypeError):
            ban_dur = 0
        
        # Extract reason
        reason = str(item.get("reason", "")).strip()

        # Create action with channel_id included
        action_type = ActionType(action_str)
        actions.append(
            ActionData(
                guild_id=guild_id,
                channel_id=channel_id,
                user_id=UserID(user_id),
                action=action_type,
                reason=reason,
                timeout_duration=timeout_dur,
                ban_duration=ban_dur,
                message_ids_to_delete=message_ids,
            )
        )
    
    logger.debug("[PARSE] Successfully parsed %d actions", len(actions))
    return actions