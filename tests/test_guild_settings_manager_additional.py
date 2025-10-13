import json
from unittest.mock import MagicMock

from modcord.configuration.guild_settings import GuildSettingsManager
from modcord.util.moderation_datatypes import ActionType, ModerationMessage


class _TestableGuildSettingsManager(GuildSettingsManager):
    """Test double that avoids starting background threads or touching disk at init."""

    def start_writer_loop(self) -> None:  # type: ignore[override]
        self.writer_loop = None
        self.writer_thread = None
        self.writer_ready.set()

    def load_from_disk(self) -> bool:  # type: ignore[override]
        # Skip disk I/O during initialization for fast, deterministic tests.
        self.guilds.clear()
        return False


def create_manager(tmp_path):
    manager = _TestableGuildSettingsManager()
    manager.data_dir = tmp_path
    manager.settings_path = tmp_path / "guild_settings.json"
    persist_mock = MagicMock(return_value=True)
    manager.schedule_persist = persist_mock  # type: ignore[assignment]
    manager.pending_writes.clear()
    return manager, persist_mock


def test_set_and_get_server_rules(tmp_path) -> None:
    manager, persist_mock = create_manager(tmp_path)

    manager.set_server_rules(100, "Be excellent to each other")

    assert manager.get_server_rules(100) == "Be excellent to each other"
    persist_mock.assert_called_once_with(100)


def test_set_action_allowed_updates_flags(tmp_path) -> None:
    manager, persist_mock = create_manager(tmp_path)

    assert manager.is_action_allowed(1, ActionType.BAN) is False

    updated = manager.set_action_allowed(1, ActionType.BAN, True)

    assert updated is True
    assert manager.is_action_allowed(1, ActionType.BAN) is True
    persist_mock.assert_called_once()

    persist_mock.reset_mock()
    # Unsupported actions should return False without scheduling persistence.
    result = manager.set_action_allowed(1, ActionType.NULL, True)
    assert result is False
    persist_mock.assert_not_called()


def test_build_payload_and_history_helpers(tmp_path) -> None:
    manager, persist_mock = create_manager(tmp_path)

    manager.set_ai_enabled(5, False)
    manager.set_server_rules(5, "No spoilers")

    message = ModerationMessage(
        message_id="m1",
        user_id="42",
        username="alice",
        content="hello",
        timestamp="2024-01-01T00:00:00Z",
        guild_id=5,
        channel_id=9,
    )
    manager.add_message_to_history(9, message)

    history = manager.get_chat_history(9)
    assert history == [message]

    payload = manager.build_payload()
    assert payload["guilds"]["5"]["ai_enabled"] is False
    assert payload["guilds"]["5"]["rules"] == "No spoilers"


def test_load_from_disk_filters_invalid_entries(tmp_path) -> None:
    manager, persist_mock = create_manager(tmp_path)

    payload = {
        "guilds": {
            "123": {"ai_enabled": False, "rules": "rule"},
            "invalid": {"ai_enabled": True},
        }
    }
    manager.settings_path.write_text(json.dumps(payload), encoding="utf-8")
    manager.load_from_disk = GuildSettingsManager.load_from_disk.__get__(manager, GuildSettingsManager)
    manager.read_settings = GuildSettingsManager.read_settings.__get__(manager, GuildSettingsManager)

    loaded = manager.load_from_disk()
    assert loaded is True
    assert 123 in manager.guilds
    assert "invalid" not in manager.guilds


def test_read_settings_returns_default_on_invalid_json(tmp_path) -> None:
    manager, _ = create_manager(tmp_path)

    manager.settings_path.write_text("not json", encoding="utf-8")

    data = manager.read_settings()
    assert data == {"guilds": {}}
