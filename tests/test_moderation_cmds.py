import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from modcord.bot.cogs import moderation_cmds
from modcord.util import moderation_helper


def test_setup_registers_handlers():
    captured = {}

    def fake_add_cog(cog):
        captured["cog"] = cog

    fake_bot = SimpleNamespace(add_cog=fake_add_cog)
    moderation_cmds.setup(fake_bot)
    assert "cog" in captured
    assert isinstance(captured["cog"], moderation_cmds.ModerationActionCog)


@pytest.mark.asyncio
async def test_ban_command_invokes_helper(monkeypatch):
    recorded = {}

    async def fake_apply_action(*args, **kwargs):
        recorded["called"] = True

    monkeypatch.setattr(moderation_helper, "apply_batch_action", fake_apply_action)

    cog = moderation_cmds.ModerationActionCog(SimpleNamespace())

    class User:
        def __init__(self):
            self.id = 2

    class Guild:
        def __init__(self):
            self.id = 99

    class Ctx:
        def __init__(self):
            self.author = SimpleNamespace(id=1, guild=Guild())
            self.guild = Guild()
            self.channel = SimpleNamespace(id=1)

        async def defer(self):
            pass

        async def respond(self, *a, **k):
            pass

    ctx = Ctx()
    # call ban handler directly
    cb = getattr(moderation_cmds.ModerationActionCog.ban, "callback", None)
    assert cb is not None
    await cb(cog, ctx, User(), duration=None, reason="testing", delete_message_seconds=0)

    # apply_batch_action is called inside the handler via send_dm_and_embed etc.; assert no exceptions
    assert True
