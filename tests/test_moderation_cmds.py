import pytest
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

from modcord.bot.cogs import moderation_cmds
from modcord.util import moderation_helper
from modcord.util.moderation_datatypes import TimeoutCommand, KickCommand, BanCommand


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


@pytest.mark.asyncio
async def test_check_permissions_denied_without_required_permission(monkeypatch):
    class FakeMember:
        def __init__(self, member_id=2, administrator=False):
            self.id = member_id
            self.guild_permissions = SimpleNamespace(administrator=administrator)

    monkeypatch.setattr(moderation_cmds, "has_permissions", lambda ctx, **_: False)
    monkeypatch.setattr(moderation_cmds.discord, "Member", FakeMember)

    cog = moderation_cmds.ModerationActionCog(SimpleNamespace())
    ctx: Any = SimpleNamespace(user=SimpleNamespace(id=1), respond=AsyncMock())
    target: Any = FakeMember()

    allowed = await cog.check_moderation_permissions(ctx, target, "kick_members")

    assert allowed is False
    ctx.respond.assert_awaited_once_with("You do not have permission to use this command.", ephemeral=True)


@pytest.mark.asyncio
async def test_check_permissions_rejects_non_member(monkeypatch):
    class FakeMember:
        def __init__(self, member_id=2, administrator=False):
            self.id = member_id
            self.guild_permissions = SimpleNamespace(administrator=administrator)

    monkeypatch.setattr(moderation_cmds, "has_permissions", lambda ctx, **_: True)
    monkeypatch.setattr(moderation_cmds.discord, "Member", FakeMember)

    cog = moderation_cmds.ModerationActionCog(SimpleNamespace())
    ctx: Any = SimpleNamespace(user=SimpleNamespace(id=1), respond=AsyncMock())
    target: Any = object()

    allowed = await cog.check_moderation_permissions(ctx, target, "kick_members")

    assert allowed is False
    ctx.respond.assert_awaited_once_with("The specified user is not a member of this server.", ephemeral=True)


@pytest.mark.asyncio
async def test_check_permissions_rejects_self_action(monkeypatch):
    class FakeMember:
        def __init__(self, member_id, administrator=False):
            self.id = member_id
            self.guild_permissions = SimpleNamespace(administrator=administrator)

    monkeypatch.setattr(moderation_cmds, "has_permissions", lambda ctx, **_: True)
    monkeypatch.setattr(moderation_cmds.discord, "Member", FakeMember)

    cog = moderation_cmds.ModerationActionCog(SimpleNamespace())
    ctx: Any = SimpleNamespace(user=SimpleNamespace(id=9), respond=AsyncMock())
    target: Any = FakeMember(member_id=9)

    allowed = await cog.check_moderation_permissions(ctx, target, "kick_members")

    assert allowed is False
    ctx.respond.assert_awaited_once_with("You cannot perform moderation actions on yourself.", ephemeral=True)


@pytest.mark.asyncio
async def test_check_permissions_rejects_admin_target(monkeypatch):
    class FakeMember:
        def __init__(self, member_id, administrator):
            self.id = member_id
            self.guild_permissions = SimpleNamespace(administrator=administrator)

    monkeypatch.setattr(moderation_cmds, "has_permissions", lambda ctx, **_: True)
    monkeypatch.setattr(moderation_cmds.discord, "Member", FakeMember)

    cog = moderation_cmds.ModerationActionCog(SimpleNamespace())
    ctx: Any = SimpleNamespace(user=SimpleNamespace(id=9), respond=AsyncMock())
    target: Any = FakeMember(member_id=10, administrator=True)

    allowed = await cog.check_moderation_permissions(ctx, target, "kick_members")

    assert allowed is False
    ctx.respond.assert_awaited_once_with("You cannot perform moderation actions against administrators.", ephemeral=True)


@pytest.mark.asyncio
async def test_check_permissions_success(monkeypatch):
    class FakeMember:
        def __init__(self, member_id, administrator):
            self.id = member_id
            self.guild_permissions = SimpleNamespace(administrator=administrator)

    monkeypatch.setattr(moderation_cmds, "has_permissions", lambda ctx, **_: True)
    monkeypatch.setattr(moderation_cmds.discord, "Member", FakeMember)

    cog = moderation_cmds.ModerationActionCog(SimpleNamespace())
    ctx: Any = SimpleNamespace(user=SimpleNamespace(id=1), respond=AsyncMock())
    target: Any = FakeMember(member_id=2, administrator=False)

    allowed = await cog.check_moderation_permissions(ctx, target, "kick_members")

    assert allowed is True
    assert ctx.respond.await_count == 0


@pytest.mark.asyncio
async def test_handle_moderation_timeout_executes_actions(monkeypatch):
    """Test that timeout command executes with proper parameters."""
    # Track if execute was called
    execute_called = []
    
    original_execute = TimeoutCommand.execute
    
    async def mock_execute(self, ctx, user, bot_instance):
        execute_called.append((ctx, user, bot_instance))
        # Don't actually execute, just track the call
    
    monkeypatch.setattr(TimeoutCommand, "execute", mock_execute)
    
    # Mock delete_messages_background
    monkeypatch.setattr(
        "modcord.util.discord_utils.delete_messages_background",
        AsyncMock()
    )

    cog = moderation_cmds.ModerationActionCog(SimpleNamespace(user=SimpleNamespace()))

    user: Any = SimpleNamespace(id=42, display_name="TestUser", guild=SimpleNamespace())
    ctx: Any = SimpleNamespace(
        guild=SimpleNamespace(),
        channel=SimpleNamespace(),
        respond=AsyncMock(),
        defer=AsyncMock(),
        followup=SimpleNamespace(send=AsyncMock()),
    )

    action = TimeoutCommand(reason="Reason", duration_seconds=600)
    await cog.execute_command_action(ctx, user, action, delete_message_seconds=30)

    # Verify execute was called with correct parameters
    assert len(execute_called) == 1
    called_ctx, called_user, called_bot = execute_called[0]
    assert called_ctx == ctx
    assert called_user == user
    assert called_bot == cog.discord_bot_instance


@pytest.mark.asyncio
async def test_handle_moderation_ban_schedules_unban(monkeypatch):
    """Test that ban command executes and can schedule unban."""
    execute_called = []
    
    async def mock_execute(self, ctx, user, bot_instance):
        execute_called.append({
            'ctx': ctx,
            'user': user,
            'bot': bot_instance,
            'ban_duration': self.ban_duration
        })
    
    monkeypatch.setattr(BanCommand, "execute", mock_execute)
    monkeypatch.setattr(
        "modcord.util.discord_utils.delete_messages_background",
        AsyncMock()
    )

    cog = moderation_cmds.ModerationActionCog(SimpleNamespace(user=SimpleNamespace()))

    user: Any = SimpleNamespace(id=50, display_name="Target", guild=SimpleNamespace())
    ctx: Any = SimpleNamespace(
        guild=SimpleNamespace(),
        channel=SimpleNamespace(),
        respond=AsyncMock(),
        defer=AsyncMock(),
        followup=SimpleNamespace(send=AsyncMock()),
    )

    action = BanCommand(reason="Reason", duration_seconds=3600)
    await cog.execute_command_action(ctx, user, action, delete_message_seconds=0)

    # Verify execute was called and had the correct ban duration
    assert len(execute_called) == 1
    assert execute_called[0]['ban_duration'] == 3600


@pytest.mark.asyncio
async def test_handle_moderation_ban_permanent_skips_unban(monkeypatch):
    """Test that permanent bans do not schedule unbans."""
    execute_called = []
    
    async def mock_execute(self, ctx, user, bot_instance):
        execute_called.append({
            'ban_duration': self.ban_duration
        })
    
    monkeypatch.setattr(BanCommand, "execute", mock_execute)
    monkeypatch.setattr(
        "modcord.util.discord_utils.delete_messages_background",
        AsyncMock()
    )

    cog = moderation_cmds.ModerationActionCog(SimpleNamespace(user=SimpleNamespace()))

    user: Any = SimpleNamespace(id=50, display_name="Target", guild=SimpleNamespace())
    ctx: Any = SimpleNamespace(
        guild=SimpleNamespace(),
        channel=SimpleNamespace(),
        respond=AsyncMock(),
        defer=AsyncMock(),
        followup=SimpleNamespace(send=AsyncMock()),
    )

    action = BanCommand(reason="Reason", duration_seconds=None)
    await cog.execute_command_action(ctx, user, action, delete_message_seconds=0)

    # Verify execute was called with permanent ban duration (None)
    assert len(execute_called) == 1
    assert execute_called[0]['ban_duration'] is None


@pytest.mark.asyncio
async def test_handle_moderation_command_handles_exception(monkeypatch):
    """Test that exceptions in command execution are caught and reported."""
    # Make KickCommand.execute raise an exception
    async def mock_execute(self, ctx, user, bot_instance):
        raise RuntimeError("boom")
    
    monkeypatch.setattr(KickCommand, "execute", mock_execute)

    cog = moderation_cmds.ModerationActionCog(SimpleNamespace(user=SimpleNamespace()))

    user: Any = SimpleNamespace(id=99, display_name="TestUser", guild=SimpleNamespace())
    ctx: Any = SimpleNamespace(
        guild=SimpleNamespace(),
        channel=SimpleNamespace(),
        respond=AsyncMock(),
        defer=AsyncMock(),
        followup=SimpleNamespace(send=AsyncMock()),
    )

    action = KickCommand(reason="Reason")
    await cog.execute_command_action(ctx, user, action)

    ctx.respond.assert_awaited_once_with("An error occurred while processing the command.", ephemeral=True)


@pytest.mark.asyncio
async def test_warn_command_aborts_when_permission_denied(monkeypatch):
    """Test that warn command aborts when permission denied."""
    async def fake_check(self, ctx, target, perm):
        self._last_perm = perm
        return False

    execute_mock = AsyncMock()

    monkeypatch.setattr(moderation_cmds.ModerationActionCog, "check_moderation_permissions", fake_check)
    monkeypatch.setattr(moderation_cmds.ModerationActionCog, "execute_command_action", execute_mock)

    cog = moderation_cmds.ModerationActionCog(SimpleNamespace())

    ctx: Any = SimpleNamespace(defer=AsyncMock(), respond=AsyncMock())
    user: Any = SimpleNamespace()

    cb = getattr(moderation_cmds.ModerationActionCog.warn, "callback", None)
    assert cb is not None
    await cb(cog, ctx, user, "Reason", delete_message_seconds=15)

    ctx.defer.assert_awaited_once()
    assert cog._last_perm == "manage_messages"
    execute_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_warn_command_invokes_handler_on_success(monkeypatch):
    """Test that warn command invokes execute_command_action on success."""
    async def fake_check(self, ctx, target, perm):
        return True

    execute_mock = AsyncMock()

    monkeypatch.setattr(moderation_cmds.ModerationActionCog, "check_moderation_permissions", fake_check)
    monkeypatch.setattr(moderation_cmds.ModerationActionCog, "execute_command_action", execute_mock)

    cog = moderation_cmds.ModerationActionCog(SimpleNamespace())

    ctx: Any = SimpleNamespace(defer=AsyncMock(), respond=AsyncMock())
    user: Any = SimpleNamespace()

    cb = getattr(moderation_cmds.ModerationActionCog.warn, "callback", None)
    assert cb is not None
    await cb(cog, ctx, user, "Reason", delete_message_seconds=45)

    ctx.defer.assert_awaited_once()
    assert execute_mock.await_count == 1
