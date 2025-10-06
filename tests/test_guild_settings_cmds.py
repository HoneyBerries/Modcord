import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from modcord.bot.cogs import guild_settings_cmds
from modcord.configuration import guild_settings


def test_setup_adds_cog():
    captured = {}

    def fake_add_cog(cog):
        captured["cog"] = cog

    fake_bot = SimpleNamespace(add_cog=fake_add_cog)
    guild_settings_cmds.setup(fake_bot)
    assert "cog" in captured
    assert isinstance(captured["cog"], guild_settings_cmds.SettingsCog)


@pytest.mark.asyncio
async def test_ai_enable_calls_manager(monkeypatch):
    called = {}

    def fake_set_ai_enabled(guild_id, enabled):
        called["args"] = (guild_id, enabled)

    monkeypatch.setattr(guild_settings.guild_settings_manager, "set_ai_enabled", fake_set_ai_enabled)

    # Call the handler directly
    cog = guild_settings_cmds.SettingsCog(SimpleNamespace())

    class Ctx:
        def __init__(self):
            self.guild_id = 10
            self.user = SimpleNamespace(guild_permissions=SimpleNamespace(manage_guild=True))

        async def respond(self, *args, **kwargs):
            pass

    ctx = Ctx()
    cb = getattr(guild_settings_cmds.SettingsCog.ai_enable, "callback", None)
    assert cb is not None
    await cb(cog, ctx)
    assert called["args"] == (10, True)
