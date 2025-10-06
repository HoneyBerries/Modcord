from modcord.util.moderation_models import (
    ActionData,
    ActionType,
    ModerationBatch,
    ModerationMessage,
)


def test_actiondata_add_and_replace_message_ids() -> None:
    action = ActionData(user_id="123", action=ActionType.WARN, reason="Initial")

    action.add_message_ids("9", " ", "10", "10", "9")

    assert action.message_ids == ["9", "10"]

    action.replace_message_ids(["5", "06", "007"])

    assert action.message_ids == ["5", "06", "007"]


def test_actiondata_to_wire_dict_includes_all_fields() -> None:
    action = ActionData(
        user_id="123",
        action=ActionType.TIMEOUT,
        reason="Break",
        message_ids=["1", "2"],
        timeout_duration=600,
        ban_duration=3600,
    )

    payload = action.to_wire_dict()

    assert payload == {
        "user_id": "123",
        "action": "timeout",
        "reason": "Break",
        "message_ids": ["1", "2"],
        "timeout_duration": 600,
        "ban_duration": 3600,
    }


def test_moderationmessage_payload_helpers() -> None:
    message = ModerationMessage(
        message_id="m1",
        user_id="42",
        username="alice",
        content="hello",
        timestamp="2024-01-01T00:00:00Z",
        guild_id=7,
        channel_id=9,
        role="assistant",
        image_summary="img",
    )

    model_payload = message.to_model_payload()
    history_payload = message.to_history_payload()

    assert model_payload == {
        "message_id": "m1",
        "user_id": "42",
        "username": "alice",
        "content": "hello",
        "timestamp": "2024-01-01T00:00:00Z",
        "image_summary": "img",
        "role": "assistant",
    }

    assert history_payload == {
        "role": "assistant",
        "user_id": "42",
        "username": "alice",
        "timestamp": "2024-01-01T00:00:00Z",
        "content": "hello",
    }


def test_moderationbatch_to_user_payload_orders_messages() -> None:
    batch = ModerationBatch(channel_id=5)

    batch.add_message(
        ModerationMessage(
            message_id="m1",
            user_id="1",
            username="alpha",
            content="first",
            timestamp="2024-01-01T10:00:00Z",
            guild_id=5,
            channel_id=5,
        )
    )
    batch.add_message(
        ModerationMessage(
            message_id="m2",
            user_id="2",
            username="bravo",
            content="second",
            timestamp="2024-01-01T09:00:00Z",
            guild_id=5,
            channel_id=5,
        )
    )
    batch.add_message(
        ModerationMessage(
            message_id="m3",
            user_id="1",
            username="alpha",
            content="third",
            timestamp="2024-01-01T12:00:00Z",
            guild_id=5,
            channel_id=5,
        )
    )

    assert batch.is_empty() is False

    user_payload = batch.to_user_payload()

    assert [entry["user_id"] for entry in user_payload] == ["2", "1"]

    alpha = next(entry for entry in user_payload if entry["user_id"] == "1")
    assert alpha["message_count"] == 2
    assert alpha["first_message_timestamp"] == "2024-01-01T10:00:00Z"
    assert alpha["latest_message_timestamp"] == "2024-01-01T12:00:00Z"
    assert [msg["message_id"] for msg in alpha["messages"]] == ["m1", "m3"]

    model_payload = batch.to_model_payload()
    assert isinstance(model_payload, list)
    assert len(model_payload) == 3
