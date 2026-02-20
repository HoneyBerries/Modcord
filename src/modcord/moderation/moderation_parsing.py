"""Utilities for parsing AI moderation responses into ActionData objects."""

from __future__ import annotations

import json
from typing import Any, List

import jsonschema
from jsonschema import ValidationError

from modcord.datatypes.action_datatypes import ActionData, ActionType, ChannelDeleteSpec
from modcord.datatypes.discord_datatypes import ChannelID, UserID, GuildID, MessageID
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
    guild_id: GuildID,
    expected_schema: dict,
) -> List[ActionData]:
    """Parse AI moderation response into ActionData objects.

    Expected response shape::

        {
          "guild_id": "...",
          "users": [
            {
              "user_id": "...",
              "action": "...",
              "reason": "...",
              "channels": [
                {"channel_id": "...", "message_ids_to_delete": ["...", ...]}
              ],
              "timeout_duration": 0,
              "ban_duration": 0
            }
          ]
        }

    Args:
        response: Raw model response text containing JSON.
        guild_id: Expected guild ID (validated against payload).
        expected_schema: JSON schema for validation.

    Returns:
        List of ActionData objects parsed from the response.
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

    # Validate against schema
    try:
        jsonschema.validate(instance=payload, schema=expected_schema)
    except ValidationError as exc:
        logger.error("[PARSE] Schema validation failed: %s", exc.message)
        return []

    # Verify guild ID matches
    response_guild = str(payload.get("guild_id", "")).strip()
    if response_guild != str(guild_id):
        logger.warning("[PARSE] Guild mismatch: expected %s, got %s", guild_id, response_guild)
        return []

    entries = payload.get("users") or []
    if not isinstance(entries, list):
        logger.error("[PARSE] 'users' field is not a list")
        return []

    logger.debug("[PARSE] Extracted %d user entries", len(entries))

    actions: List[ActionData] = []

    for item in entries:
        if type(item) is not dict:
            continue

        user_id = str(item.get("user_id", "")).strip()
        action_str = str(item.get("action", "null")).lower()

        # ---- parse per-channel deletions ----
        raw_channels = item.get("channels") or []
        channel_deletions: List[ChannelDeleteSpec] = []
        if isinstance(raw_channels, list):
            for ch_entry in raw_channels:
                if not isinstance(ch_entry, dict):
                    continue
                ch_id_str = str(ch_entry.get("channel_id", "")).strip()
                if not ch_id_str:
                    continue
                raw_mids = ch_entry.get("message_ids_to_delete") or []
                mids = tuple(MessageID(mid) for mid in raw_mids if mid) if isinstance(raw_mids, list) else ()
                channel_deletions.append(
                    ChannelDeleteSpec(
                        channel_id=ChannelID(ch_id_str),
                        message_ids=mids,
                    )
                )

        # ---- durations ----
        try:
            timeout_dur = int(item["timeout_duration"]) if item.get("timeout_duration") is not None and item["timeout_duration"] != "" else None
        except (ValueError, TypeError):
            timeout_dur = None

        try:
            ban_dur = int(item["ban_duration"]) if item.get("ban_duration") is not None and item["ban_duration"] != "" else None
        except (ValueError, TypeError):
            ban_dur = None

        reason = str(item.get("reason", "")).strip()

        try:
            action_type = ActionType(action_str)
        except ValueError:
            logger.warning("[PARSE] Unknown action type %r for user %s, defaulting to null", action_str, user_id)
            action_type = ActionType.NULL

        actions.append(
            ActionData(
                guild_id=guild_id,
                user_id=UserID(user_id),
                action=action_type,
                reason=reason,
                timeout_duration=timeout_dur,
                ban_duration=ban_dur,
                channel_deletions=tuple(channel_deletions),
            )
        )

    logger.debug("[PARSE] Successfully parsed %d actions", len(actions))
    return actions