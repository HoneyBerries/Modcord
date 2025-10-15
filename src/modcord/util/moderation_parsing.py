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
from typing import Any, List, Optional

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


def _strip_code_fences(payload: str) -> str:
    """Drop Markdown code fences so JSON can be parsed normally."""
    if "```" not in payload:
        return payload
    return "\n".join(ln for ln in payload.splitlines() if not ln.strip().startswith("```"))


def _extract_json_payload(raw: str) -> Any:
    """Return the JSON value embedded in ``raw`` or raise ``ValueError``."""
    cleaned = _strip_code_fences(raw.strip())
    last_close = max(cleaned.rfind("}"), cleaned.rfind("]"))
    if last_close == -1:
        raise ValueError("no JSON object found")

    for start in range(last_close, -1, -1):
        if cleaned[start] not in "{[":
            continue
        snippet = cleaned[start : last_close + 1]
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            continue

    raise ValueError("unable to decode JSON payload")


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
        payload = _extract_json_payload(assistant_response)
    except ValueError:
        return ActionType("null"), "invalid JSON response"

    if not isinstance(payload, dict):
        return ActionType("null"), "invalid JSON response"

    action_value = str(payload.get("action", "null")).lower()
    reason = str(payload.get("reason", "Automated moderation action"))

    if action_value in VALID_ACTION_VALUES:
        return ActionType(action_value), reason

    return ActionType("null"), "unknown action type"


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
        payload = _extract_json_payload(assistant_response)
    except ValueError:
        return []

    if not isinstance(payload, dict):
        return []

    try:
        _moderation_validator.validate(payload)
    except ValidationError as exc:
        logger.warning("Batch response failed schema validation: %s", exc.message)
        return []

    response_channel = str(payload.get("channel_id", "")).strip()
    if response_channel and response_channel != str(channel_id):
        logger.warning(
            "Batch response channel mismatch: expected %s, got %s",
            channel_id,
            response_channel,
        )
        return []

    entries = payload.get("users") or []
    if not isinstance(entries, list):
        return []

    def _coerce_int(value: Any) -> Optional[int]:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    validated: dict[str, ActionData] = {}

    for item in entries:
        if not isinstance(item, dict):
            continue

        user_id = str(item.get("user_id", "")).strip()
        action_value = str(item.get("action", "null")).lower()
        if not user_id or action_value not in VALID_ACTION_VALUES:
            continue

        reason = str(item.get("reason", "Automated moderation action"))
        raw_ids = item.get("message_ids_to_delete") or []
        message_ids = [str(mid) for mid in raw_ids] if isinstance(raw_ids, list) else []

        timeout_duration = _coerce_int(item.get("timeout_duration"))
        ban_duration = _coerce_int(item.get("ban_duration"))

        action_enum = ActionType(action_value)
        existing = validated.get(user_id)

        if existing is None:
            validated[user_id] = ActionData(
                user_id,
                action_enum,
                reason,
                message_ids,
                timeout_duration,
                ban_duration,
            )
            continue

        if existing.action == ActionType.NULL and action_enum != ActionType.NULL:
            existing.action = action_enum
            existing.reason = reason
        elif action_enum != ActionType.NULL and reason:
            existing.reason = reason

        existing.add_message_ids(*message_ids)

        if timeout_duration is not None:
            existing.timeout_duration = timeout_duration
        if ban_duration is not None:
            existing.ban_duration = ban_duration

    return list(validated.values())
