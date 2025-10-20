import sqlite3
import asyncio
import pytest
from unittest.mock import MagicMock

from modcord.configuration.guild_settings import GuildSettingsManager
from modcord.util.moderation_datatypes import ActionType, ModerationMessage


class _TestableGuildSettingsManager(GuildSettingsManager):
    """Test double that avoids database I/O at init."""

    async def load_from_disk(self) -> bool:  # type: ignore[override]
        # Skip disk I/O during initialization for fast, deterministic tests.
        self.guilds.clear()
        return False


async def create_manager(tmp_path):
    # Override DB_PATH for testing
    import modcord.configuration.database as db_module
    db_module.DB_PATH = tmp_path / "test.db"
    
    manager = _TestableGuildSettingsManager()
    
    # Mock _trigger_persist to track calls
    persist_mock = MagicMock()
    
    def mock_trigger(guild_id: int) -> None:
        persist_mock(guild_id)
    
    manager._trigger_persist = mock_trigger  # type: ignore[assignment]
    return manager, persist_mock


@pytest.mark.asyncio
async def test_set_and_get_server_rules(tmp_path) -> None:
    manager, persist_mock = await create_manager(tmp_path)

    manager.set_server_rules(100, "Be excellent to each other")

    assert manager.get_server_rules(100) == "Be excellent to each other"
    persist_mock.assert_called_once_with(100)


@pytest.mark.asyncio
async def test_set_action_allowed_updates_flags(tmp_path) -> None:
    manager, persist_mock = await create_manager(tmp_path)

    # BAN is now enabled by default
    assert manager.is_action_allowed(1, ActionType.BAN) is True

    # Disable it
    updated = manager.set_action_allowed(1, ActionType.BAN, False)

    assert updated is True
    assert manager.is_action_allowed(1, ActionType.BAN) is False
    persist_mock.assert_called_once()

    persist_mock.reset_mock()
    # Unsupported actions should return False without scheduling persistence.
    result = manager.set_action_allowed(1, ActionType.NULL, True)
    assert result is False
    persist_mock.assert_not_called()


@pytest.mark.asyncio
async def test_build_payload_and_history_helpers(tmp_path) -> None:
    manager, persist_mock = await create_manager(tmp_path)

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
    # Use message_history_cache.get_cached_messages(9) if you want to check cache contents

    payload = manager.build_payload()
    assert payload["guilds"]["5"]["ai_enabled"] is False
    assert payload["guilds"]["5"]["rules"] == "No spoilers"


@pytest.mark.asyncio
async def test_load_from_disk_filters_invalid_entries(tmp_path) -> None:
    """Test that load_from_disk handles database errors gracefully."""
    import modcord.configuration.database as db_module
    db_module.DB_PATH = tmp_path / "test.db"
    
    manager = _TestableGuildSettingsManager()
    
    # Create database with test data including a valid entry
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id INTEGER PRIMARY KEY,
            ai_enabled INTEGER NOT NULL DEFAULT 1,
            rules TEXT NOT NULL DEFAULT '',
            auto_warn_enabled INTEGER NOT NULL DEFAULT 1,
            auto_delete_enabled INTEGER NOT NULL DEFAULT 1,
            auto_timeout_enabled INTEGER NOT NULL DEFAULT 1,
            auto_kick_enabled INTEGER NOT NULL DEFAULT 1,
            auto_ban_enabled INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        INSERT INTO guild_settings (guild_id, ai_enabled, rules)
        VALUES (?, ?, ?)
    """, (123, 0, "rule"))
    conn.commit()
    conn.close()
    
    # Restore the original load_from_disk method
    manager.load_from_disk = GuildSettingsManager.load_from_disk.__get__(manager, GuildSettingsManager)
    
    loaded = await manager.load_from_disk()
    assert loaded is True
    assert 123 in manager.guilds
    assert manager.guilds[123].ai_enabled is False
    assert manager.guilds[123].rules == "rule"


@pytest.mark.asyncio
async def test_load_from_empty_database(tmp_path) -> None:
    """Test that load_from_disk handles empty database correctly."""
    import modcord.configuration.database as db_module
    db_module.DB_PATH = tmp_path / "test.db"
    
    manager = _TestableGuildSettingsManager()
    
    # Create an empty database
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id INTEGER PRIMARY KEY,
            ai_enabled INTEGER NOT NULL DEFAULT 1,
            rules TEXT NOT NULL DEFAULT '',
            auto_warn_enabled INTEGER NOT NULL DEFAULT 1,
            auto_delete_enabled INTEGER NOT NULL DEFAULT 1,
            auto_timeout_enabled INTEGER NOT NULL DEFAULT 1,
            auto_kick_enabled INTEGER NOT NULL DEFAULT 1,
            auto_ban_enabled INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    
    # Restore the original load_from_disk method
    manager.load_from_disk = GuildSettingsManager.load_from_disk.__get__(manager, GuildSettingsManager)
    
    loaded = await manager.load_from_disk()
    assert loaded is False  # No data loaded
    assert len(manager.guilds) == 0
