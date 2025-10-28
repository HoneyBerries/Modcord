"""Tests for guild_settings module."""

import pytest
import tempfile
import os
from pathlib import Path

from modcord.configuration.guild_settings import (
    GuildSettings,
    GuildSettingsManager,
    ACTION_FLAG_FIELDS,
)
from modcord.moderation.moderation_datatypes import ActionType


@pytest.fixture
async def temp_db():
    """Create a temporary database for testing."""
    from modcord.database import database
    
    # Save original DB path
    original_path = database.DB_PATH
    
    # Create temporary database
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    temp_file.close()
    database.DB_PATH = Path(temp_file.name)
    
    # Initialize database
    await database.init_database()
    
    yield database.DB_PATH
    
    # Cleanup
    database.DB_PATH = original_path
    try:
        os.unlink(temp_file.name)
    except:
        pass


class TestGuildSettings:
    """Tests for GuildSettings dataclass."""

    def test_guild_settings_initialization(self):
        """Test GuildSettings initialization with defaults."""
        settings = GuildSettings(guild_id=123456)
        
        assert settings.guild_id == 123456
        assert settings.ai_enabled is True
        assert settings.rules == ""
        assert settings.auto_warn_enabled is True
        assert settings.auto_delete_enabled is True
        assert settings.auto_timeout_enabled is True
        assert settings.auto_kick_enabled is True
        assert settings.auto_ban_enabled is True

    def test_guild_settings_custom_values(self):
        """Test GuildSettings with custom values."""
        settings = GuildSettings(
            guild_id=123456,
            ai_enabled=False,
            rules="No spam",
            auto_ban_enabled=False
        )
        
        assert settings.ai_enabled is False
        assert settings.rules == "No spam"
        assert settings.auto_ban_enabled is False


class TestActionFlagFields:
    """Tests for ACTION_FLAG_FIELDS constant."""

    def test_action_flag_fields_mapping(self):
        """Test that ACTION_FLAG_FIELDS has correct mappings."""
        assert ACTION_FLAG_FIELDS[ActionType.WARN] == "auto_warn_enabled"
        assert ACTION_FLAG_FIELDS[ActionType.DELETE] == "auto_delete_enabled"
        assert ACTION_FLAG_FIELDS[ActionType.TIMEOUT] == "auto_timeout_enabled"
        assert ACTION_FLAG_FIELDS[ActionType.KICK] == "auto_kick_enabled"
        assert ACTION_FLAG_FIELDS[ActionType.BAN] == "auto_ban_enabled"

    def test_action_flag_fields_completeness(self):
        """Test that all relevant action types are mapped."""
        assert len(ACTION_FLAG_FIELDS) == 5


class TestGuildSettingsManager:
    """Tests for GuildSettingsManager class."""

    def test_manager_initialization(self):
        """Test GuildSettingsManager initialization."""
        manager = GuildSettingsManager()
        
        assert isinstance(manager.guilds, dict)
        assert len(manager.guilds) == 0
        assert len(manager.channel_guidelines) == 0

    def test_ensure_guild_creates_new(self):
        """Test ensure_guild creates new settings if not exists."""
        manager = GuildSettingsManager()
        
        settings = manager.ensure_guild(123456)
        
        assert settings.guild_id == 123456
        assert 123456 in manager.guilds

    def test_ensure_guild_returns_existing(self):
        """Test ensure_guild returns existing settings."""
        manager = GuildSettingsManager()
        
        first_call = manager.ensure_guild(123456)
        second_call = manager.ensure_guild(123456)
        
        assert first_call is second_call

    def test_get_guild_settings(self):
        """Test get_guild_settings returns settings."""
        manager = GuildSettingsManager()
        
        settings = manager.get_guild_settings(123456)
        
        assert settings.guild_id == 123456

    def test_list_guild_ids(self):
        """Test list_guild_ids returns all guild IDs."""
        manager = GuildSettingsManager()
        
        manager.ensure_guild(111)
        manager.ensure_guild(222)
        manager.ensure_guild(333)
        
        guild_ids = manager.list_guild_ids()
        
        assert len(guild_ids) == 3
        assert 111 in guild_ids
        assert 222 in guild_ids
        assert 333 in guild_ids

    def test_get_server_rules_existing(self):
        """Test getting rules for existing guild."""
        manager = GuildSettingsManager()
        
        settings = manager.ensure_guild(123)
        settings.rules = "Test rules"
        
        rules = manager.get_server_rules(123)
        
        assert rules == "Test rules"

    def test_get_server_rules_nonexistent(self):
        """Test getting rules for nonexistent guild returns empty string."""
        manager = GuildSettingsManager()
        
        rules = manager.get_server_rules(999)
        
        assert rules == ""

    def test_set_server_rules(self):
        """Test setting server rules."""
        manager = GuildSettingsManager()
        
        manager.set_server_rules(123, "No spam allowed")
        
        assert manager.guilds[123].rules == "No spam allowed"

    def test_set_server_rules_none(self):
        """Test setting None rules converts to empty string."""
        manager = GuildSettingsManager()
        
        manager.set_server_rules(123, None)
        
        assert manager.guilds[123].rules == ""

    def test_get_channel_guidelines_existing(self):
        """Test getting channel guidelines."""
        manager = GuildSettingsManager()
        
        manager.channel_guidelines[123][456] = "Channel specific rules"
        
        guidelines = manager.get_channel_guidelines(123, 456)
        
        assert guidelines == "Channel specific rules"

    def test_get_channel_guidelines_nonexistent(self):
        """Test getting nonexistent channel guidelines returns empty string."""
        manager = GuildSettingsManager()
        
        guidelines = manager.get_channel_guidelines(999, 888)
        
        assert guidelines == ""

    def test_set_channel_guidelines(self):
        """Test setting channel guidelines."""
        manager = GuildSettingsManager()
        
        manager.set_channel_guidelines(123, 456, "Be nice")
        
        assert manager.channel_guidelines[123][456] == "Be nice"

    def test_set_channel_guidelines_none(self):
        """Test setting None guidelines converts to empty string."""
        manager = GuildSettingsManager()
        
        manager.set_channel_guidelines(123, 456, None)
        
        assert manager.channel_guidelines[123][456] == ""

    def test_is_ai_enabled_default(self):
        """Test AI enabled returns True by default."""
        manager = GuildSettingsManager()
        
        assert manager.is_ai_enabled(123) is True

    def test_is_ai_enabled_disabled(self):
        """Test AI enabled returns False when disabled."""
        manager = GuildSettingsManager()
        
        manager.ensure_guild(123).ai_enabled = False
        
        assert manager.is_ai_enabled(123) is False

    def test_set_ai_enabled(self):
        """Test setting AI enabled state."""
        manager = GuildSettingsManager()
        
        result = manager.set_ai_enabled(123, False)
        
        assert result is True
        assert manager.guilds[123].ai_enabled is False

    def test_is_action_allowed_default(self):
        """Test action allowed returns True by default."""
        manager = GuildSettingsManager()
        
        assert manager.is_action_allowed(123, ActionType.WARN) is True
        assert manager.is_action_allowed(123, ActionType.BAN) is True

    def test_is_action_allowed_disabled(self):
        """Test action allowed returns False when disabled."""
        manager = GuildSettingsManager()
        
        settings = manager.ensure_guild(123)
        settings.auto_ban_enabled = False
        
        assert manager.is_action_allowed(123, ActionType.BAN) is False

    def test_is_action_allowed_unsupported_action(self):
        """Test unsupported action type returns True."""
        manager = GuildSettingsManager()
        
        assert manager.is_action_allowed(123, ActionType.NULL) is True
        assert manager.is_action_allowed(123, ActionType.UNBAN) is True

    def test_set_action_allowed(self):
        """Test setting action allowed state."""
        manager = GuildSettingsManager()
        
        result = manager.set_action_allowed(123, ActionType.KICK, False)
        
        assert result is True
        assert manager.guilds[123].auto_kick_enabled is False

    def test_set_action_allowed_unsupported(self):
        """Test setting unsupported action returns False."""
        manager = GuildSettingsManager()
        
        result = manager.set_action_allowed(123, ActionType.NULL, False)
        
        assert result is False

    async def test_persist_guild(self, temp_db):
        """Test persisting guild to database."""
        manager = GuildSettingsManager()
        await manager.async_init()
        
        manager.ensure_guild(123)
        manager.set_server_rules(123, "Test rules")
        
        result = await manager.persist_guild(123)
        
        assert result is True

    async def test_persist_guild_nonexistent(self, temp_db):
        """Test persisting nonexistent guild returns False."""
        manager = GuildSettingsManager()
        await manager.async_init()
        
        result = await manager.persist_guild(999)
        
        assert result is False

    async def test_load_from_disk(self, temp_db):
        """Test loading settings from disk."""
        from modcord.database.database import get_connection
        
        # Insert test data
        async with get_connection() as db:
            await db.execute("""
                INSERT INTO guild_settings 
                (guild_id, ai_enabled, rules, auto_warn_enabled, auto_delete_enabled,
                 auto_timeout_enabled, auto_kick_enabled, auto_ban_enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (123, 1, "Test rules", 1, 1, 1, 0, 1))
            await db.commit()
        
        manager = GuildSettingsManager()
        await manager.async_init()
        
        settings = manager.get_guild_settings(123)
        assert settings.rules == "Test rules"
        assert settings.auto_kick_enabled is False

    async def test_async_init(self, temp_db):
        """Test async initialization."""
        manager = GuildSettingsManager()
        
        await manager.async_init()
        
        assert manager._db_initialized is True

    async def test_async_init_only_once(self, temp_db):
        """Test async init only happens once."""
        manager = GuildSettingsManager()
        
        await manager.async_init()
        await manager.async_init()
        
        # Should not raise error, just skip second init
        assert manager._db_initialized is True
