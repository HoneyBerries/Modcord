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
    """Test settings panel displays correct AI status."""
    called = {}

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

    # Call the handler directly
    cog = guild_settings_cmds.GuildSettingsCog(SimpleNamespace())

    class Ctx:
        def __init__(self):
            self.guild_id = 10
            self.user = SimpleNamespace(guild_permissions=SimpleNamespace(manage_guild=True))
            self.interaction = SimpleNamespace(original_response=AsyncMock())

        async def respond(self, *args, **kwargs):
            self.response_args = (args, kwargs)

    ctx = Ctx()
    cb = getattr(guild_settings_cmds.GuildSettingsCog.settings_panel, "callback", None)
    assert cb is not None
    await cb(cog, ctx)
    # Verify respond was called with an embed
    assert hasattr(ctx, "response_args")
    assert "embed" in ctx.response_args[1]


@pytest.mark.asyncio
async def test_ai_enable_requires_guild_context(monkeypatch):
    """Test settings panel requires guild context."""
    calls = []

    cog = guild_settings_cmds.GuildSettingsCog(SimpleNamespace())

    class Ctx:
        def __init__(self):
            self.guild_id = None
            self.user = SimpleNamespace(guild_permissions=SimpleNamespace(manage_guild=True))
            self.respond = AsyncMock()

    ctx = Ctx()
    cb = getattr(guild_settings_cmds.GuildSettingsCog.settings_panel, "callback", None)
    assert cb is not None
    await cb(cog, ctx)

    ctx.respond.assert_awaited_once_with("This command can only be used in a server.", ephemeral=True)


@pytest.mark.asyncio
async def test_ai_enable_requires_manage_permission(monkeypatch):
    """Test settings panel requires manage permission."""
    calls = []

    cog = guild_settings_cmds.GuildSettingsCog(SimpleNamespace())

    class Ctx:
        def __init__(self):
            self.guild_id = 123
            self.user = SimpleNamespace(guild_permissions=SimpleNamespace(manage_guild=False))
            self.respond = AsyncMock()

    ctx = Ctx()
    cb = getattr(guild_settings_cmds.GuildSettingsCog.settings_panel, "callback", None)
    assert cb is not None
    await cb(cog, ctx)

    assert ctx.respond.await_count == 1
    call = ctx.respond.await_args
    assert call is not None
    message = call.args[0] if call.args else call.kwargs.get("content", "")
    kwargs = call.kwargs
    assert "permission" in message.lower() or "Manage Server" in message
    assert kwargs.get("ephemeral") is True


@pytest.mark.asyncio
async def test_ai_disable_calls_manager(monkeypatch):
    """Test settings panel can display disabled AI status."""
    def fake_get_settings(guild_id):
        from types import SimpleNamespace
        return SimpleNamespace(
            ai_enabled=False,
            rules="",
            auto_warn_enabled=False,
            auto_delete_enabled=False,
            auto_timeout_enabled=False,
            auto_kick_enabled=False,
            auto_ban_enabled=True,
        )

    monkeypatch.setattr(guild_settings.guild_settings_manager, "get_guild_settings", fake_get_settings)

    cog = guild_settings_cmds.GuildSettingsCog(SimpleNamespace())

    class Ctx:
        def __init__(self):
            self.guild_id = 77
            self.user = SimpleNamespace(guild_permissions=SimpleNamespace(manage_guild=True))
            self.respond = AsyncMock()
            self.interaction = SimpleNamespace(original_response=AsyncMock())

    ctx = Ctx()
    cb = getattr(guild_settings_cmds.GuildSettingsCog.settings_panel, "callback", None)
    assert cb is not None
    await cb(cog, ctx)

    ctx.respond.assert_awaited_once()


@pytest.mark.asyncio
async def test_ai_status_reports_manager_value(monkeypatch):
    """Test settings panel shows correct AI status in embed."""
    def fake_get_settings(guild_id):
        from types import SimpleNamespace
        assert guild_id == 900
        return SimpleNamespace(
            ai_enabled=False,
            rules="",
            auto_warn_enabled=False,
            auto_delete_enabled=False,
            auto_timeout_enabled=False,
            auto_kick_enabled=False,
            auto_ban_enabled=True,
        )

    monkeypatch.setattr(guild_settings.guild_settings_manager, "get_guild_settings", fake_get_settings)

    cog = guild_settings_cmds.GuildSettingsCog(SimpleNamespace())

    class Ctx:
        def __init__(self):
            self.guild_id = 900
            self.user = SimpleNamespace(guild_permissions=SimpleNamespace(manage_guild=True))
            self.respond = AsyncMock()
            self.interaction = SimpleNamespace(original_response=AsyncMock())

    ctx = Ctx()
    cb = getattr(guild_settings_cmds.GuildSettingsCog.settings_panel, "callback", None)
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
    assert "disabled" in fields["AI Moderation"].lower() or "❌" in fields["AI Moderation"]


@pytest.mark.asyncio
async def test_ai_set_action_updates_manager(monkeypatch):
    """Test that action toggles are displayed in the settings panel."""
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

    def fake_is_action_allowed(guild_id, action):
        # Return different values for different actions
        from modcord.util.moderation_datatypes import ActionType
        if action == ActionType.WARN:
            return False
        return True

    monkeypatch.setattr(guild_settings.guild_settings_manager, "get_guild_settings", fake_get_settings)
    monkeypatch.setattr(guild_settings.guild_settings_manager, "is_action_allowed", fake_is_action_allowed)

    cog = guild_settings_cmds.GuildSettingsCog(SimpleNamespace())

    class Ctx:
        def __init__(self):
            self.guild_id = 44
            self.user = SimpleNamespace(guild_permissions=SimpleNamespace(manage_guild=True))
            self.respond = AsyncMock()
            self.interaction = SimpleNamespace(original_response=AsyncMock())

    ctx = Ctx()
    cb = getattr(guild_settings_cmds.GuildSettingsCog.settings_panel, "callback", None)
    assert cb is not None
    await cb(cog, ctx)

    assert ctx.respond.await_count == 1
    call = ctx.respond.await_args
    assert call is not None
    kwargs = call.kwargs
    embed = kwargs.get("embed")
    assert embed is not None
    # Check that embed has Automatic Actions field
    fields = {f.name: f.value for f in embed.fields}
    assert "Automatic Actions" in fields


@pytest.mark.asyncio
async def test_ai_set_action_rejects_unknown_action(monkeypatch):
    """Test that settings panel can be shown - action toggling is handled in the UI layer."""
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

    cog = guild_settings_cmds.GuildSettingsCog(SimpleNamespace())

    class Ctx:
        def __init__(self):
            self.guild_id = 81
            self.user = SimpleNamespace(guild_permissions=SimpleNamespace(manage_guild=True))
            self.respond = AsyncMock()
            self.interaction = SimpleNamespace(original_response=AsyncMock())

    ctx = Ctx()
    cb = getattr(guild_settings_cmds.GuildSettingsCog.settings_panel, "callback", None)
    assert cb is not None
    await cb(cog, ctx)

    ctx.respond.assert_awaited_once()


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
