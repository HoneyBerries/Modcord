"""Utilities for parsing AI moderation responses.

This module centralizes logic that interprets the model's assistant
responses into structured moderation instructions. The functions are
pure (no side effects) and intentionally written to be easy to unit test.

Public exports
- VALID_ACTION_VALUES: set[str] — allowed action names (matches :class:`ActionType` values)
- moderation_schema: dict — JSON schema used to guide model output
- parse_action(assistant_response: str) -> tuple[ActionType, str]
    Parse a single-action JSON object and return ``(ActionType, reason)``.
- parse_batch_actions(assistant_response: str, channel_id: int) -> List[ActionData]
    Parse a batched response and return a list of :class:`ActionData` objects.

Notes
- Functions tolerate fenced code blocks (```), loose text around JSON, and
  common type variations (e.g., numeric message IDs coerced to strings).
- On parse error ``parse_batch_actions`` returns an empty list.

Example usage
    assistant_text = '```json\n{"channel_id": "42", "actions": [...] }\n```'
    actions = await parse_batch_actions(assistant_text, channel_id=42)

"""
from __future__ import annotations

import json
import logging
from typing import List

from jsonschema import Draft7Validator, ValidationError

from modcord.util.moderation_datatypes import ActionData, ActionType

logger = logging.getLogger("moderation_parsing")

VALID_ACTION_VALUES: set[str] = {action.value for action in ActionType}
"""Set of action strings that are considered valid moderation responses."""

moderation_schema = {
    "type": "object",
    "properties": {
        "channel_id": {"type": "string"},
        "users": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "action": {
                        "type": "string",
                        "enum": ["null", "delete", "warn", "timeout", "kick", "ban"],
                    },
                    "reason": {"type": "string"},
                    "message_ids_to_delete": {"type": "array", "items": {"type": "string"}},
                    "timeout_duration": {"type": ["integer", "null"]},
                    "ban_duration": {"type": ["integer", "null"]},
                },
                "required": [
                    "user_id",
                    "action",
                    "reason",
                    "message_ids_to_delete",
                    "timeout_duration",
                    "ban_duration",
                ],
                "additionalProperties": False,
            },
            "minItems": 0,
        },
    },
    "required": ["channel_id", "users"],
    "additionalProperties": False,
}
"""JSON schema guiding the structure of model-generated moderation responses."""


_moderation_validator = Draft7Validator(moderation_schema)


async def parse_action(assistant_response: str) -> tuple[ActionType, str]:
    """Parse a single-action assistant response into ``(ActionType, reason)``.

    Parameters
    ----------
    assistant_response:
        Raw assistant text returned by the model. The parser tolerates fenced
        code blocks, leading/trailing commentary, or minor formatting issues
        around the JSON payload. For Qwen3-Thinking models, this may include
        reasoning text before the JSON output.

    Returns
    -------
    tuple[ActionType, str]
        Resolved action enumeration and associated reason. Falls back to
        ``(ActionType.NULL, "invalid JSON response")`` on parse failure.
    """
    try:
        s = assistant_response.strip()
        # Remove fenced code blocks
        if s.startswith('```'):
            s = '\n'.join([ln for ln in s.splitlines() if not ln.strip().startswith('```')])
        
        # Extract the last complete JSON object (handles reasoning prefix)
        # Find all potential JSON start positions
        json_starts = []
        for i, char in enumerate(s):
            if char in ('{', '['):
                json_starts.append((i, char))
        
        if not json_starts:
            return ActionType('null'), "invalid JSON response"
        
        # Try parsing from the last JSON start backwards
        parsed = None
        for start_idx, start_char in reversed(json_starts):
            end_char = '}' if start_char == '{' else ']'
            # Find matching end brace
            for end_idx in range(len(s) - 1, start_idx, -1):
                if s[end_idx] == end_char:
                    try:
                        candidate = s[start_idx:end_idx + 1]
                        parsed = json.loads(candidate)
                        if isinstance(parsed, dict):
                            break
                    except (json.JSONDecodeError, ValueError):
                        continue
            if parsed and isinstance(parsed, dict):
                break
        
        if not parsed:
            return ActionType('null'), "invalid JSON response"
        
        if isinstance(parsed, dict):
            action_value = str(parsed.get('action', 'null')).lower()
            reason = str(parsed.get('reason', 'Automated moderation action'))
            if action_value in VALID_ACTION_VALUES:
                return ActionType(action_value), reason
            return ActionType('null'), "unknown action type"
    except Exception as e:
        logger.warning(f"Failed to parse JSON response: {e}")
        return ActionType('null'), "invalid JSON response"
    return ActionType('null'), "invalid JSON response"


async def parse_batch_actions(assistant_response: str, channel_id: int) -> List[ActionData]:
    """Translate a batched moderation payload into ``ActionData`` objects.

    Parameters
    ----------
    assistant_response:
        Model response text that should contain a JSON object describing
        channel ID and per-user actions. For Qwen3-Thinking models, this
        may include reasoning text before the JSON output.
    channel_id:
        Expected channel identifier; mismatches trigger an empty result.

    Returns
    -------
    list[ActionData]
        Ordered list of validated moderation actions. An empty list indicates
        schema validation failure or other parsing issues.
    """
    try:
        s = assistant_response.strip()
        # Remove fenced code blocks
        if s.startswith('```'):
            s = '\n'.join([ln for ln in s.splitlines() if not ln.strip().startswith('```')])
        
        # Extract the last complete JSON object (handles reasoning prefix)
        # Find all potential JSON start positions
        json_starts = []
        for i, char in enumerate(s):
            if char in ('{', '['):
                json_starts.append((i, char))
        
        # Try parsing from the last JSON start backwards
        parsed = None
        for start_idx, start_char in reversed(json_starts):
            end_char = '}' if start_char == '{' else ']'
            # Find matching end brace
            for end_idx in range(len(s) - 1, start_idx, -1):
                if s[end_idx] == end_char:
                    try:
                        candidate = s[start_idx:end_idx + 1]
                        parsed = json.loads(candidate)
                        if isinstance(parsed, dict) and 'users' in parsed:
                            break
                    except (json.JSONDecodeError, ValueError):
                        continue
            if parsed and isinstance(parsed, dict) and 'users' in parsed:
                break

        if not isinstance(parsed, dict):
            logger.warning("Batch response is not a JSON object; ignoring.")
            return []

        users_payload = parsed.get("users")

        try:
            _moderation_validator.validate(parsed)
        except ValidationError as exc:
            logger.warning("Batch response failed schema validation: %s", exc.message)
            return []

        response_channel = str(parsed.get("channel_id", "")).strip()
        if response_channel and response_channel != str(channel_id):
            logger.warning(
                "Batch response channel mismatch: expected %s, got %s",
                channel_id,
                response_channel,
            )
            return []
        entries = users_payload or []

        validated_map: dict[str, ActionData] = {}

        for a in entries:
            if not isinstance(a, dict):
                continue
            user_id = str(a.get('user_id', '')).strip()
            action_value = str(a.get('action', 'null')).lower()
            if not user_id or action_value not in VALID_ACTION_VALUES:
                continue

            reason = str(a.get('reason', 'Automated moderation action'))

            raw_message_ids = a.get('message_ids_to_delete') or []
            if isinstance(raw_message_ids, list):
                message_ids = [str(mid) for mid in raw_message_ids if str(mid).strip()]
            else:
                message_ids = []

            timeout_duration = a.get('timeout_duration')
            if timeout_duration is not None:
                try:
                    timeout_duration = int(timeout_duration)
                except (TypeError, ValueError):
                    timeout_duration = None

            ban_duration = a.get('ban_duration')
            if ban_duration is not None:
                try:
                    ban_duration = int(ban_duration)
                except (TypeError, ValueError):
                    ban_duration = None

            try:
                action_enum = ActionType(action_value)
            except ValueError:
                # Should not occur due to VALID_ACTION_VALUES check, but guard anyway
                continue

            existing = validated_map.get(user_id)
            if existing is None:
                validated_map[user_id] = ActionData(
                    user_id,
                    action_enum,
                    reason,
                    message_ids,
                    timeout_duration,
                    ban_duration,
                )
                continue

            # Merge duplicate entries defensively: prefer non-null actions and accumulate IDs.
            if existing.action == ActionType.NULL and action_enum != ActionType.NULL:
                existing.action = action_enum
                existing.reason = reason
            elif action_enum != ActionType.NULL:
                existing.reason = reason or existing.reason

            existing.add_message_ids(*message_ids)

            if timeout_duration is not None:
                existing.timeout_duration = timeout_duration
            if ban_duration is not None:
                existing.ban_duration = ban_duration

        return list(validated_map.values())
    except Exception as e:
        logger.error(f"Error parsing batch actions: {e}")
        return []
