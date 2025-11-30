from datetime import datetime, timedelta, timezone
from modcord.datatypes.discord_datatypes import GuildID, UserID
import modcord.util.format_utils as format_utils
from modcord.datatypes.action_datatypes import ActionData, ActionType


def test_humanize_timestamp_converts_naive_to_utc():
    naive_value = datetime(2025, 1, 3, 12, 34, 56)

    result = format_utils.humanize_timestamp(naive_value)

    assert result == "2025-01-03 12:34:56 UTC"
def test_humanize_timestamp_normalizes_timezones():
    eastern = timezone(timedelta(hours=-5))
    aware_value = datetime(2024, 1, 1, 7, 30, tzinfo=eastern)

    result = format_utils.humanize_timestamp(aware_value)

    assert result == "2024-01-01 12:30:00 UTC"


def test_humanize_timestamp_clamps_future_values(monkeypatch):
    future_value = datetime.now(timezone.utc) + timedelta(hours=1)
    warnings = []

    def fake_warning(*args, **kwargs):
        warnings.append((args, kwargs))

    monkeypatch.setattr(format_utils.logger, "warning", fake_warning)

    result = format_utils.humanize_timestamp(future_value)
    parsed = datetime.strptime(result, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)

    assert parsed <= datetime.now(timezone.utc)
    assert warnings, "humanize_timestamp should log when clamping future values"


def test_format_past_actions_handles_timeout_durations():
    actions = [
        ActionData(
            guild_id=GuildID.from_int(1),
            user_id=UserID.from_int(10),
            action=ActionType.TIMEOUT,
            reason="spam",
            timeout_duration=15,
        ),
        ActionData(
            guild_id=GuildID.from_int(1),
            user_id=UserID.from_int(11),
            action=ActionType.TIMEOUT,
            reason="harassment",
            timeout_duration=-1,
        ),
    ]

    formatted = format_utils.format_past_actions(actions)

    assert formatted[0] == {
        "action": "timeout",
        "reason": "spam",
        "duration": "15 minutes",
    }
    assert formatted[1]["duration"] == "permanent"


def test_format_past_actions_handles_ban_durations_and_omits_duration_when_absent():
    actions = [
        ActionData(
            guild_id=GuildID.from_int(1),
            user_id=UserID.from_int(20),
            action=ActionType.BAN,
            reason="severe abuse",
            ban_duration=-1,
        ),
        ActionData(
            guild_id=GuildID.from_int(1),
            user_id=UserID.from_int(21),
            action=ActionType.BAN,
            reason="alts",
            ban_duration=0,
        ),
        ActionData(
            guild_id=GuildID.from_int(1),
            user_id=UserID.from_int(22),
            action=ActionType.BAN,
            reason="temporary block",
            ban_duration=45,
        ),
        ActionData(
            guild_id=GuildID.from_int(1),
            user_id=UserID.from_int(23),
            action=ActionType.WARN,
            reason="reminder only",
        ),
    ]

    formatted = format_utils.format_past_actions(actions)

    assert formatted[0]["duration"] == "permanent"
    assert formatted[1]["duration"] == "permanent"
    assert formatted[2]["duration"] == "45 minutes"
    assert "duration" not in formatted[3]