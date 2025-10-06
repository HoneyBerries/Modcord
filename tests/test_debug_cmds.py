import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock

from modcord.bot.cogs import debug_cmds


def test_setup_registers_commands(monkeypatch):
    captured = {}

    def fake_add_cog(cog):
        captured["cog"] = cog

    fake_bot = SimpleNamespace(add_cog=fake_add_cog, latency=0.123)
    debug_cmds.setup(fake_bot)

    assert "cog" in captured
    assert isinstance(captured["cog"], debug_cmds.DebugCog)


@pytest.mark.asyncio
async def test_test_command_responds(monkeypatch):
    sent = {}

    class AppCtx:
        def __init__(self):
            self.guild = None

        async def respond(self, *args, **kwargs):
            sent["args"] = args
            sent["kwargs"] = kwargs

    fake_bot = SimpleNamespace(latency=0.05)
    cog = debug_cmds.DebugCog(fake_bot)
    ctx = AppCtx()
    # runtime call; cast to expected type for clarity
    # call the underlying function that the slash decorator wraps
    cb = getattr(debug_cmds.DebugCog.test, "callback", None)
    assert cb is not None
    await cb(cog, ctx)
    assert "Round Trip Time" in str(sent["args"][0])
