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
    assert isinstance(captured["cog"], guild_settings_cmds.GuildSettingsCog)


@pytest.mark.asyncio
async def test_ai_enable_calls_manager(monkeypatch):
    called = {}

    def fake_set_ai_enabled(guild_id, enabled):
        called["args"] = (guild_id, enabled)

    monkeypatch.setattr(guild_settings.guild_settings_manager, "set_ai_enabled", fake_set_ai_enabled)

    # Call the handler directly
    cog = guild_settings_cmds.GuildSettingsCog(SimpleNamespace())

    class Ctx:
        def __init__(self):
            self.guild_id = 10
            self.user = SimpleNamespace(guild_permissions=SimpleNamespace(manage_guild=True))

        async def respond(self, *args, **kwargs):
            pass

    ctx = Ctx()
    cb = getattr(guild_settings_cmds.GuildSettingsCog.ai_enable, "callback", None)
    assert cb is not None
    await cb(cog, ctx)
    assert called["args"] == (10, True)


@pytest.mark.asyncio
async def test_ai_enable_requires_guild_context(monkeypatch):
    calls = []

    def fake_set_ai_enabled(*args):
        calls.append(args)

    manager = SimpleNamespace(set_ai_enabled=fake_set_ai_enabled)
    monkeypatch.setattr(guild_settings_cmds, "guild_settings_manager", manager)

    cog = guild_settings_cmds.GuildSettingsCog(SimpleNamespace())

    class Ctx:
        def __init__(self):
            self.guild_id = None
            self.user = SimpleNamespace(guild_permissions=SimpleNamespace(manage_guild=True))
            self.respond = AsyncMock()

    ctx = Ctx()
    cb = getattr(guild_settings_cmds.GuildSettingsCog.ai_enable, "callback", None)
    assert cb is not None
    await cb(cog, ctx)

    ctx.respond.assert_awaited_once_with("This command can only be used in a server.", ephemeral=True)
    assert calls == []


@pytest.mark.asyncio
async def test_ai_enable_requires_manage_permission(monkeypatch):
    calls = []

    def fake_set_ai_enabled(*args):
        calls.append(args)

    manager = SimpleNamespace(set_ai_enabled=fake_set_ai_enabled)
    monkeypatch.setattr(guild_settings_cmds, "guild_settings_manager", manager)

    cog = guild_settings_cmds.GuildSettingsCog(SimpleNamespace())

    class Ctx:
        def __init__(self):
            self.guild_id = 123
            self.user = SimpleNamespace(guild_permissions=SimpleNamespace(manage_guild=False))
            self.respond = AsyncMock()

    ctx = Ctx()
    cb = getattr(guild_settings_cmds.GuildSettingsCog.ai_enable, "callback", None)
    assert cb is not None
    await cb(cog, ctx)

    assert ctx.respond.await_count == 1
    call = ctx.respond.await_args
    assert call is not None
    message = call.args[0]
    kwargs = call.kwargs
    assert "permission" in message.lower()
    assert kwargs.get("ephemeral") is True
    assert calls == []


@pytest.mark.asyncio
async def test_ai_disable_calls_manager(monkeypatch):
    calls = []

    def fake_set_ai_enabled(guild_id, enabled):
        calls.append((guild_id, enabled))

    manager = SimpleNamespace(set_ai_enabled=fake_set_ai_enabled)
    monkeypatch.setattr(guild_settings_cmds, "guild_settings_manager", manager)

    cog = guild_settings_cmds.GuildSettingsCog(SimpleNamespace())

    class Ctx:
        def __init__(self):
            self.guild_id = 77
            self.user = SimpleNamespace(guild_permissions=SimpleNamespace(manage_guild=True))
            self.respond = AsyncMock()

    ctx = Ctx()
    cb = getattr(guild_settings_cmds.GuildSettingsCog.ai_disable, "callback", None)
    assert cb is not None
    await cb(cog, ctx)

    assert calls == [(77, False)]
    ctx.respond.assert_awaited_once()


@pytest.mark.asyncio
async def test_ai_status_reports_manager_value(monkeypatch):
    def fake_is_ai_enabled(guild_id):
        assert guild_id == 900
        return False

    manager = SimpleNamespace(is_ai_enabled=fake_is_ai_enabled)
    monkeypatch.setattr(guild_settings_cmds, "guild_settings_manager", manager)

    cog = guild_settings_cmds.GuildSettingsCog(SimpleNamespace())

    class Ctx:
        def __init__(self):
            self.guild_id = 900
            self.respond = AsyncMock()

    ctx = Ctx()
    cb = getattr(guild_settings_cmds.GuildSettingsCog.ai_status, "callback", None)
    assert cb is not None
    await cb(cog, ctx)

    # New behaviour: status is returned as an embed in the response
    ctx.respond.assert_awaited_once()
    call = ctx.respond.await_args
    assert call is not None
    kwargs = call.kwargs
    embed = kwargs.get("embed")
    assert embed is not None
    # Embed should contain AI Moderation field set to disabled
    fields = {f.name: f.value for f in embed.fields}
    assert "AI Moderation" in fields
    assert "disabled" in fields["AI Moderation"].lower()


@pytest.mark.asyncio
async def test_ai_set_action_updates_manager(monkeypatch):
    calls = []

    def fake_set_action_allowed(guild_id, action, enabled):
        calls.append((guild_id, action, enabled))

    manager = SimpleNamespace(set_action_allowed=fake_set_action_allowed)
    monkeypatch.setattr(guild_settings_cmds, "guild_settings_manager", manager)

    cog = guild_settings_cmds.GuildSettingsCog(SimpleNamespace())

    class Ctx:
        def __init__(self):
            self.guild_id = 44
            self.user = SimpleNamespace(guild_permissions=SimpleNamespace(manage_guild=True))
            self.respond = AsyncMock()

    ctx = Ctx()
    cb = getattr(guild_settings_cmds.GuildSettingsCog.ai_set_action, "callback", None)
    assert cb is not None
    await cb(cog, ctx, action="warn", enabled=False)

    assert len(calls) == 1
    guild_id, action_type, enabled = calls[0]
    assert guild_id == 44
    assert action_type.name == "WARN"
    assert enabled is False
    assert ctx.respond.await_count == 1
    call = ctx.respond.await_args
    assert call is not None
    kwargs = call.kwargs
    # The panel response includes a short flash content describing the change
    content = kwargs.get("content") if kwargs.get("content") is not None else (call.args[0] if call.args else None)
    assert content is not None
    assert "disabled" in content.lower()
    assert kwargs.get("ephemeral") is True


@pytest.mark.asyncio
async def test_ai_set_action_rejects_unknown_action(monkeypatch):
    calls = []

    def fake_set_action_allowed(*args):
        calls.append(args)

    manager = SimpleNamespace(set_action_allowed=fake_set_action_allowed)
    monkeypatch.setattr(guild_settings_cmds, "guild_settings_manager", manager)

    cog = guild_settings_cmds.GuildSettingsCog(SimpleNamespace())

    class Ctx:
        def __init__(self):
            self.guild_id = 81
            self.user = SimpleNamespace(guild_permissions=SimpleNamespace(manage_guild=True))
            self.respond = AsyncMock()

    ctx = Ctx()
    cb = getattr(guild_settings_cmds.GuildSettingsCog.ai_set_action, "callback", None)
    assert cb is not None
    await cb(cog, ctx, action="invalid", enabled=True)

    assert calls == []
    ctx.respond.assert_awaited_once_with("Unsupported action.", ephemeral=True)


@pytest.mark.asyncio
async def test_settings_dump_requires_guild(monkeypatch):
    manager = SimpleNamespace(get_guild_settings=lambda _: None)
    monkeypatch.setattr(guild_settings_cmds, "guild_settings_manager", manager)

    cog = guild_settings_cmds.GuildSettingsCog(SimpleNamespace())

    class Ctx:
        def __init__(self):
            self.guild_id = None
            self.respond = AsyncMock()

    ctx = Ctx()
    cb = getattr(guild_settings_cmds.GuildSettingsCog.settings_dump, "callback", None)
    assert cb is not None
    await cb(cog, ctx)

    ctx.respond.assert_awaited_once_with("This command can only be used in a server.", ephemeral=True)


@pytest.mark.asyncio
async def test_settings_dump_uses_followup_on_interaction_responded(monkeypatch):
    class FakeInteractionResponded(Exception):
        pass

    guild_settings = SimpleNamespace(
        ai_enabled=True,
        rules="rule",
        auto_warn_enabled=True,
        auto_delete_enabled=False,
        auto_timeout_enabled=True,
        auto_kick_enabled=False,
        auto_ban_enabled=False,
    )

    manager = SimpleNamespace(get_guild_settings=lambda gid: guild_settings)
    monkeypatch.setattr(guild_settings_cmds, "guild_settings_manager", manager)
    monkeypatch.setattr(guild_settings_cmds.discord, "InteractionResponded", FakeInteractionResponded)
    monkeypatch.setattr(guild_settings_cmds.discord, "File", lambda fp, filename: {"fp": fp, "filename": filename})

    cog = guild_settings_cmds.GuildSettingsCog(SimpleNamespace())

    class Ctx:
        def __init__(self):
            self.guild_id = 555
            self.respond = AsyncMock(side_effect=FakeInteractionResponded())
            self.followup = SimpleNamespace(send=AsyncMock())

    ctx = Ctx()
    cb = getattr(guild_settings_cmds.GuildSettingsCog.settings_dump, "callback", None)
    assert cb is not None
    await cb(cog, ctx)

    assert ctx.followup.send.await_count == 1
    call = ctx.followup.send.await_args
    assert call is not None
    args = call.args
    kwargs = call.kwargs
    file_kw = kwargs.get("file")
    assert isinstance(file_kw, dict)
    assert file_kw["filename"] == "guild_555_settings.json"
    assert kwargs.get("ephemeral") is True
