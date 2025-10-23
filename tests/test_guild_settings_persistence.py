import os
import shutil
import tempfile
import asyncio
import sqlite3
import pytest
from pathlib import Path
from modcord.configuration import guild_settings
from modcord.database.database import DB_PATH

@pytest.mark.asyncio
async def test_database_initialization(tmp_path):
    """Test that database is initialized correctly."""
    # Temporarily override DB_PATH
    import modcord.database.database as db_module
    original_path = db_module.DB_PATH
    db_module.DB_PATH = tmp_path / "test.db"
    
    try:
        mgr = guild_settings.GuildSettingsManager()
        await mgr.async_init()
        
        # Check that database file exists
        assert db_module.DB_PATH.exists()
        
        # Check that tables exist
        conn = sqlite3.connect(db_module.DB_PATH)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        assert "guild_settings" in tables
        assert "schema_version" in tables
        
        await mgr.shutdown()
    finally:
        db_module.DB_PATH = original_path

@pytest.mark.asyncio
async def test_schedule_persist_and_persist_guild(tmp_path):
    """Test persisting guild settings to database."""
    # Temporarily override DB_PATH
    import modcord.database.database as db_module
    original_path = db_module.DB_PATH
    db_module.DB_PATH = tmp_path / "test.db"
    
    try:
        mgr = guild_settings.GuildSettingsManager()
        await mgr.async_init()
        
        # Add a guild and persist
        gid = 12345
        mgr.set_ai_enabled(gid, True)
        assert mgr.schedule_persist(gid) is True
        await asyncio.sleep(0.1)  # Let persistence complete
        
        # Verify data in database
        conn = sqlite3.connect(db_module.DB_PATH)
        cursor = conn.execute("SELECT guild_id, ai_enabled FROM guild_settings WHERE guild_id = ?", (gid,))
        row = cursor.fetchone()
        conn.close()
        
        assert row is not None
        assert row[0] == gid
        assert row[1] == 1  # True stored as 1
        
        # Test persist_guild (async)
        mgr.set_server_rules(gid, "test rules")
        await asyncio.sleep(0.1)  # Let persistence complete
        
        ok = await mgr.persist_guild(gid)
        assert ok is True
        
        # Verify rules in database
        conn = sqlite3.connect(db_module.DB_PATH)
        cursor = conn.execute("SELECT rules FROM guild_settings WHERE guild_id = ?", (gid,))
        row = cursor.fetchone()
        conn.close()
        
        assert row is not None
        assert row[0] == "test rules"
        
        await mgr.shutdown()
    finally:
        db_module.DB_PATH = original_path

@pytest.mark.asyncio
async def test_load_from_disk(tmp_path):
    """Test loading guild settings from database."""
    # Temporarily override DB_PATH
    import modcord.database.database as db_module
    original_path = db_module.DB_PATH
    db_module.DB_PATH = tmp_path / "test.db"
    
    try:
        # Create a database with test data
        gid = 54321
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
        """, (gid, 0, "abc"))
        conn.commit()
        conn.close()
        
        # Create manager and load from database
        mgr = guild_settings.GuildSettingsManager()
        result = await mgr.load_from_disk()
        assert result is True
        
        s = mgr.get_guild_settings(gid)
        assert s.guild_id == gid
        assert s.ai_enabled is False
        assert s.rules == "abc"
        
        await mgr.shutdown()
    finally:
        db_module.DB_PATH = original_path
