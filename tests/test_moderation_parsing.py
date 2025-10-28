"""Tests for moderation_parsing module."""

import pytest
import json
from modcord.moderation.moderation_parsing import (
    build_dynamic_moderation_schema,
    parse_batch_actions,
)
from modcord.moderation.moderation_datatypes import ActionType


class TestBuildDynamicModerationSchema:
    """Tests for build_dynamic_moderation_schema function."""

    def test_empty_user_message_map(self):
        """Test schema with empty user message map."""
        schema = build_dynamic_moderation_schema({}, "channel123")
        assert schema["type"] == "object"
        assert "channel_id" in schema["properties"]
        assert schema["properties"]["channel_id"]["enum"] == ["channel123"]
        assert schema["properties"]["users"]["minItems"] == 0
        assert schema["properties"]["users"]["maxItems"] == 0

    def test_single_user_schema(self):
        """Test schema with single user."""
        user_message_map = {
            "user1": ["msg1", "msg2"]
        }
        schema = build_dynamic_moderation_schema(user_message_map, "channel123")
        
        assert schema["type"] == "object"
        assert "channel_id" in schema["properties"]
        assert "users" in schema["properties"]
        assert schema["properties"]["users"]["minItems"] == 1
        assert schema["properties"]["users"]["maxItems"] == 1
        
        # Check user schema structure
        user_schemas = schema["properties"]["users"]["items"]["oneOf"]
        assert len(user_schemas) == 1
        assert user_schemas[0]["properties"]["user_id"]["enum"] == ["user1"]
        assert user_schemas[0]["properties"]["message_ids_to_delete"]["items"]["enum"] == ["msg1", "msg2"]

    def test_multiple_users_schema(self):
        """Test schema with multiple users."""
        user_message_map = {
            "user1": ["msg1", "msg2"],
            "user2": ["msg3"],
            "user3": []
        }
        schema = build_dynamic_moderation_schema(user_message_map, "channel456")
        
        assert schema["properties"]["users"]["minItems"] == 3
        assert schema["properties"]["users"]["maxItems"] == 3
        
        user_schemas = schema["properties"]["users"]["items"]["oneOf"]
        assert len(user_schemas) == 3

    def test_schema_action_types(self):
        """Test that schema includes all action types."""
        user_message_map = {"user1": ["msg1"]}
        schema = build_dynamic_moderation_schema(user_message_map, "channel1")
        
        user_schema = schema["properties"]["users"]["items"]["oneOf"][0]
        action_enum = user_schema["properties"]["action"]["enum"]
        
        assert "null" in action_enum
        assert "delete" in action_enum
        assert "warn" in action_enum
        assert "timeout" in action_enum
        assert "kick" in action_enum
        assert "ban" in action_enum

    def test_schema_required_fields(self):
        """Test that schema has all required fields."""
        user_message_map = {"user1": []}
        schema = build_dynamic_moderation_schema(user_message_map, "channel1")
        
        assert "channel_id" in schema["required"]
        assert "users" in schema["required"]
        
        user_schema = schema["properties"]["users"]["items"]["oneOf"][0]
        required = user_schema["required"]
        assert "user_id" in required
        assert "action" in required
        assert "reason" in required
        assert "message_ids_to_delete" in required
        assert "timeout_duration" in required
        assert "ban_duration" in required

    def test_schema_no_additional_properties(self):
        """Test that schema disallows additional properties."""
        user_message_map = {"user1": []}
        schema = build_dynamic_moderation_schema(user_message_map, "channel1")
        
        assert schema["additionalProperties"] is False
        user_schema = schema["properties"]["users"]["items"]["oneOf"][0]
        assert user_schema["additionalProperties"] is False


class TestParseBatchActions:
    """Tests for parse_batch_actions function."""

    def test_parse_valid_response(self):
        """Test parsing valid moderation response."""
        user_message_map = {
            "user1": ["msg1", "msg2"],
            "user2": ["msg3"]
        }
        schema = build_dynamic_moderation_schema(user_message_map, "123")
        
        response = json.dumps({
            "channel_id": "123",
            "users": [
                {
                    "user_id": "user1",
                    "action": "warn",
                    "reason": "Spam",
                    "message_ids_to_delete": ["msg1"],
                    "timeout_duration": 0,
                    "ban_duration": 0
                },
                {
                    "user_id": "user2",
                    "action": "null",
                    "reason": "No issues",
                    "message_ids_to_delete": [],
                    "timeout_duration": 0,
                    "ban_duration": 0
                }
            ]
        })
        
        actions = parse_batch_actions(response, 123, schema)
        assert len(actions) == 2
        assert actions[0].user_id == "user1"
        assert actions[0].action == ActionType.WARN
        assert actions[0].reason == "Spam"
        assert actions[0].message_ids == ["msg1"]
        assert actions[1].user_id == "user2"
        assert actions[1].action == ActionType.NULL

    def test_parse_timeout_action(self):
        """Test parsing timeout action with duration."""
        user_message_map = {"user1": ["msg1"]}
        schema = build_dynamic_moderation_schema(user_message_map, "123")
        
        response = json.dumps({
            "channel_id": "123",
            "users": [
                {
                    "user_id": "user1",
                    "action": "timeout",
                    "reason": "Harassment",
                    "message_ids_to_delete": ["msg1"],
                    "timeout_duration": 30,
                    "ban_duration": 0
                }
            ]
        })
        
        actions = parse_batch_actions(response, 123, schema)
        assert len(actions) == 1
        assert actions[0].action == ActionType.TIMEOUT
        assert actions[0].timeout_duration == 30

    def test_parse_ban_action(self):
        """Test parsing ban action with duration."""
        user_message_map = {"user1": []}
        schema = build_dynamic_moderation_schema(user_message_map, "123")
        
        response = json.dumps({
            "channel_id": "123",
            "users": [
                {
                    "user_id": "user1",
                    "action": "ban",
                    "reason": "Serious violation",
                    "message_ids_to_delete": [],
                    "timeout_duration": 0,
                    "ban_duration": 1440
                }
            ]
        })
        
        actions = parse_batch_actions(response, 123, schema)
        assert len(actions) == 1
        assert actions[0].action == ActionType.BAN
        assert actions[0].ban_duration == 1440

    def test_parse_permanent_ban(self):
        """Test parsing permanent ban (ban_duration = -1)."""
        user_message_map = {"user1": []}
        schema = build_dynamic_moderation_schema(user_message_map, "123")
        
        response = json.dumps({
            "channel_id": "123",
            "users": [
                {
                    "user_id": "user1",
                    "action": "ban",
                    "reason": "Permanent ban",
                    "message_ids_to_delete": [],
                    "timeout_duration": 0,
                    "ban_duration": -1
                }
            ]
        })
        
        actions = parse_batch_actions(response, 123, schema)
        assert len(actions) == 1
        assert actions[0].ban_duration == -1

    def test_parse_invalid_json(self):
        """Test parsing invalid JSON returns empty list."""
        schema = build_dynamic_moderation_schema({"user1": []}, "123")
        response = "not valid json"
        
        actions = parse_batch_actions(response, 123, schema)
        assert actions == []

    def test_parse_non_dict_payload(self):
        """Test parsing non-dict payload returns empty list."""
        schema = build_dynamic_moderation_schema({"user1": []}, "123")
        response = json.dumps(["not", "a", "dict"])
        
        actions = parse_batch_actions(response, 123, schema)
        assert actions == []

    def test_parse_wrong_channel_id(self):
        """Test parsing with wrong channel ID returns empty list."""
        user_message_map = {"user1": []}
        schema = build_dynamic_moderation_schema(user_message_map, "123")
        
        response = json.dumps({
            "channel_id": "456",  # Wrong channel ID
            "users": [
                {
                    "user_id": "user1",
                    "action": "null",
                    "reason": "",
                    "message_ids_to_delete": [],
                    "timeout_duration": 0,
                    "ban_duration": 0
                }
            ]
        })
        
        actions = parse_batch_actions(response, 123, schema)
        assert actions == []

    def test_parse_missing_users_field(self):
        """Test parsing with missing users field returns empty list."""
        schema = build_dynamic_moderation_schema({"user1": []}, "123")
        response = json.dumps({"channel_id": "123"})
        
        actions = parse_batch_actions(response, 123, schema)
        assert actions == []

    def test_parse_empty_reason(self):
        """Test parsing with empty reason string."""
        user_message_map = {"user1": []}
        schema = build_dynamic_moderation_schema(user_message_map, "123")
        
        response = json.dumps({
            "channel_id": "123",
            "users": [
                {
                    "user_id": "user1",
                    "action": "null",
                    "reason": "",
                    "message_ids_to_delete": [],
                    "timeout_duration": 0,
                    "ban_duration": 0
                }
            ]
        })
        
        actions = parse_batch_actions(response, 123, schema)
        assert len(actions) == 1
        assert actions[0].reason == ""

    def test_parse_multiple_actions(self):
        """Test parsing response with multiple different actions."""
        user_message_map = {
            "user1": ["msg1"],
            "user2": ["msg2"],
            "user3": []
        }
        schema = build_dynamic_moderation_schema(user_message_map, "123")
        
        response = json.dumps({
            "channel_id": "123",
            "users": [
                {
                    "user_id": "user1",
                    "action": "delete",
                    "reason": "Spam",
                    "message_ids_to_delete": ["msg1"],
                    "timeout_duration": 0,
                    "ban_duration": 0
                },
                {
                    "user_id": "user2",
                    "action": "kick",
                    "reason": "Rule violation",
                    "message_ids_to_delete": [],
                    "timeout_duration": 0,
                    "ban_duration": 0
                },
                {
                    "user_id": "user3",
                    "action": "null",
                    "reason": "OK",
                    "message_ids_to_delete": [],
                    "timeout_duration": 0,
                    "ban_duration": 0
                }
            ]
        })
        
        actions = parse_batch_actions(response, 123, schema)
        assert len(actions) == 3
        assert actions[0].action == ActionType.DELETE
        assert actions[1].action == ActionType.KICK
        assert actions[2].action == ActionType.NULL

    def test_parse_zero_duration(self):
        """Test parsing with zero duration."""
        user_message_map = {"user1": []}
        schema = build_dynamic_moderation_schema(user_message_map, "123")
        
        response = json.dumps({
            "channel_id": "123",
            "users": [
                {
                    "user_id": "user1",
                    "action": "warn",
                    "reason": "Test",
                    "message_ids_to_delete": [],
                    "timeout_duration": 0,
                    "ban_duration": 0
                }
            ]
        })
        
        actions = parse_batch_actions(response, 123, schema)
        assert actions[0].timeout_duration == 0
        assert actions[0].ban_duration == 0
