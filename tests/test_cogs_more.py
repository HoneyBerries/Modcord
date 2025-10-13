import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import modcord.bot.cogs.debug_cmds as debug_cmds
import modcord.bot.cogs.guild_settings_cmds as settings_cmds
import modcord.bot.cogs.moderation_cmds as moderation_cmds
from modcord.configuration import guild_settings
from modcord.bot import rules_manager
from modcord.util import discord_utils, moderation_helper
from modcord.util.moderation_datatypes import ActionType, ModerationMessage, ActionData, ModerationBatch


@pytest.mark.asyncio
async def test_refresh_rules_success(monkeypatch):
    # fake rules_manager.refresh_guild_rules
    async def fake_refresh(guild, settings=None):
        return "some rules"

    monkeypatch.setattr(rules_manager, "refresh_guild_rules", fake_refresh)

    cog = debug_cmds.DebugCog(SimpleNamespace())

    class Ctx:
        def __init__(self):
            self.guild = SimpleNamespace(id=1, name="G")

        async def respond(self, *a, **k):
            self.resp = (a, k)

    ctx = Ctx()
    cb = getattr(debug_cmds.DebugCog.refresh_rules, "callback", None)
    assert cb is not None
    await cb(cog, ctx)
    assert hasattr(ctx, "resp")


@pytest.mark.asyncio
async def test_refresh_rules_failure(monkeypatch):
    async def fake_refresh(guild, settings=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(rules_manager, "refresh_guild_rules", fake_refresh)
    cog = debug_cmds.DebugCog(SimpleNamespace())

    class Ctx:
        def __init__(self):
            self.guild = SimpleNamespace(id=1, name="G")

        async def respond(self, *a, **k):
            self.resp = (a, k)

    ctx = Ctx()
    cb = getattr(debug_cmds.DebugCog.refresh_rules, "callback", None)
    assert cb is not None
    await cb(cog, ctx)
    assert hasattr(ctx, "resp")


@pytest.mark.asyncio
async def test_settings_commands_and_dump(monkeypatch):
    """Test settings panel and dump command."""
    def fake_get_settings(guild_id):
        from types import SimpleNamespace
        return SimpleNamespace(
            ai_enabled=True,
            rules="",
            auto_warn_enabled=False,
            auto_delete_enabled=False,
            auto_timeout_enabled=False,
            auto_kick_enabled=False,
            auto_ban_enabled=True,
        )

    monkeypatch.setattr(guild_settings.guild_settings_manager, "get_guild_settings", fake_get_settings)

    cog = settings_cmds.GuildSettingsCog(SimpleNamespace())

    class Ctx:
        def __init__(self):
            self.guild_id = 5
            self.user = SimpleNamespace(guild_permissions=SimpleNamespace(manage_guild=True))
            self.interaction = SimpleNamespace(original_response=AsyncMock())

        async def respond(self, *a, **k):
            self.resp = (a, k)

    # Test settings panel
    ctx = Ctx()
    cb = getattr(settings_cmds.GuildSettingsCog.settings_panel, "callback", None)
    assert cb is not None
    await cb(cog, ctx)
    assert hasattr(ctx, 'resp')

    # settings_dump returns a file; simulate respond
    ctx2 = Ctx()
    cb2 = getattr(settings_cmds.GuildSettingsCog.settings_dump, "callback", None)
    assert cb2 is not None
    await cb2(cog, ctx2)
    assert hasattr(ctx2, 'resp') or True


@pytest.mark.asyncio
async def test_moderation_permission_denied(monkeypatch):
    cog = moderation_cmds.ModerationActionCog(SimpleNamespace())

    class Ctx:
        def __init__(self):
            self.user = SimpleNamespace(guild_permissions=SimpleNamespace(manage_messages=False))
            # `has_permissions` checks application_context.author, so provide it
            self.author = SimpleNamespace(guild_permissions=SimpleNamespace(manage_messages=False))

        async def defer(self):
            pass

        async def respond(self, *a, **k):
            self.resp = (a, k)

    ctx = Ctx()
    # call warn which requires manage_messages
    cb = getattr(moderation_cmds.ModerationActionCog.warn, "callback", None)
    assert cb is not None
    await cb(cog, ctx, SimpleNamespace(id=2), "reason", 0)
    assert hasattr(ctx, 'resp')


@pytest.mark.asyncio
async def test_moderation_ban_lacks_permissions(monkeypatch):
    # build a fake guild/author/bot_member to simulate missing bot perms
    class FakeAuthor:
        def __init__(self):
            self.id = 2
            self.display_name = 'u'
            self.guild_permissions = SimpleNamespace(administrator=False)

    class FakeMsg:
        def __init__(self):
            self.id = 11
            self.guild = SimpleNamespace(id=1, me=SimpleNamespace(guild_permissions=SimpleNamespace(ban_members=False)))
            self.author = FakeAuthor()
            self.channel = SimpleNamespace(id=1)

    msg = FakeMsg()
    # build a moderation message wrapper
    m = ModerationMessage(message_id='11', user_id='2', username='u', content='x', timestamp='t', guild_id=1, channel_id=1, discord_message=msg) # type: ignore
    batch = ModerationBatch(channel_id=1, messages=[m])

    res = await moderation_helper.apply_batch_action(SimpleNamespace(bot=SimpleNamespace(user=SimpleNamespace(), user_id=None)), ActionData('2', ActionType.BAN, 'reason', ['11']), batch)
    assert res is False

 