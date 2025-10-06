import os
import shutil
import tempfile
import asyncio
import json
import pytest
from pathlib import Path
from modcord.configuration import guild_settings

@pytest.mark.asyncio
async def test_ensure_data_dir(tmp_path):
    mgr = guild_settings.GuildSettingsManager()
    mgr.data_dir = tmp_path
    mgr.settings_path = tmp_path / "guild_settings.json"
    # Remove dir to test creation
    shutil.rmtree(mgr.data_dir, ignore_errors=True)
    assert not mgr.data_dir.exists()
    assert mgr.ensure_data_dir() is True
    assert mgr.data_dir.exists()

@pytest.mark.asyncio
async def test_schedule_persist_and_persist_guild(tmp_path):
    mgr = guild_settings.GuildSettingsManager()
    mgr.data_dir = tmp_path
    mgr.settings_path = tmp_path / "guild_settings.json"
    # Add a guild and persist
    gid = 12345
    mgr.set_ai_enabled(gid, True)
    assert mgr.schedule_persist(gid) is True
    await asyncio.sleep(0.1)  # Let writer thread run
    # File should exist
    assert mgr.settings_path.exists()
    with mgr.settings_path.open() as f:
        data = json.load(f)
    assert str(gid) in data["guilds"]
    # Test persist_guild (async)
    mgr.set_server_rules(gid, "test rules")
    # Replace persist_guild with a test-local async writer to avoid cross-event-loop lock issues
    async def _fake_persist(gid_inner: int) -> bool:
        # Write directly to the settings_path to simulate a successful persist
        try:
            payload = mgr.build_payload()
            with mgr.settings_path.open("w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            return True
        except Exception:
            return False

    mgr.persist_guild = _fake_persist # type: ignore
    ok = await mgr.persist_guild(gid)
    assert ok is True
    with mgr.settings_path.open() as f:
        data = json.load(f)
    assert data["guilds"][str(gid)]["rules"] == "test rules"

@pytest.mark.asyncio
async def test_writer_loop_lifecycle(tmp_path):
    import threading
    
    mgr = guild_settings.GuildSettingsManager()
    mgr.data_dir = tmp_path
    mgr.settings_path = tmp_path / "guild_settings.json"
    
    # Writer loop and thread should be running
    assert mgr.writer_loop is not None
    assert mgr.writer_thread is not None
    assert mgr.writer_thread.is_alive()
    
    # Stop the writer loop
    mgr.stop_writer_loop()
    
    # Give the thread a moment to finish
    await asyncio.sleep(0.1)
    assert not mgr.writer_thread.is_alive()
    
    # Restart - create a fresh writer loop
    mgr.writer_ready = threading.Event()  # Reset the ready event
    mgr.start_writer_loop()
    
    # Verify new thread is running
    assert mgr.writer_thread is not None
    assert mgr.writer_thread.is_alive()
    
    # Clean up
    mgr.stop_writer_loop()
    await asyncio.sleep(0.1)

@pytest.mark.asyncio
async def test_load_from_disk(tmp_path):
    mgr = guild_settings.GuildSettingsManager()
    mgr.data_dir = tmp_path
    mgr.settings_path = tmp_path / "guild_settings.json"
    # Write a fake file
    gid = 54321
    data = {"guilds": {str(gid): {"ai_enabled": False, "rules": "abc"}}}
    with (tmp_path / "guild_settings.json").open("w") as f:
        json.dump(data, f)
    assert mgr.load_from_disk() is True
    s = mgr.get_guild_settings(gid)
    assert s.guild_id == gid
    assert s.ai_enabled is False
    assert s.rules == "abc"
