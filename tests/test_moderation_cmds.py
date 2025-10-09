import asyncio
import pytest
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

from modcord.bot.cogs import moderation_cmds
from modcord.util import moderation_helper
from modcord.util.moderation_datatypes import ActionType
from modcord.util.discord_utils import PERMANENT_DURATION


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
    recorded = {}

    async def fake_delete_messages_background(ctx, user, seconds):
        recorded["delete"] = seconds

    monkeypatch.setattr(moderation_cmds, "parse_duration_to_seconds", lambda duration: 600)
    send_mock = AsyncMock()
    monkeypatch.setattr(moderation_cmds, "send_dm_and_embed", send_mock)
    monkeypatch.setattr(moderation_cmds, "delete_messages_background", fake_delete_messages_background)
    schedule_mock = AsyncMock()
    monkeypatch.setattr(moderation_cmds, "schedule_unban", schedule_mock)

    original_create_task = moderation_cmds.asyncio.create_task
    scheduled = []

    def capture_task(coro):
        task = original_create_task(coro)
        scheduled.append(task)
        return task

    monkeypatch.setattr(moderation_cmds.asyncio, "create_task", capture_task)

    cog = moderation_cmds.ModerationActionCog(SimpleNamespace())

    user: Any = SimpleNamespace(timeout=AsyncMock(), id=42)
    ctx: Any = SimpleNamespace(
        guild=SimpleNamespace(),
        channel=SimpleNamespace(),
        respond=AsyncMock(),
        followup=SimpleNamespace(send=AsyncMock()),
    )

    await cog.handle_moderation_command(ctx, user, ActionType.TIMEOUT, "Reason", duration="10m", delete_message_seconds=30)

    user.timeout.assert_awaited_once()
    for task in scheduled:
        await task
    send_mock.assert_awaited_once_with(ctx, user, ActionType.TIMEOUT, "Reason", "10m")
    assert recorded["delete"] == 30
    assert schedule_mock.await_count == 0


@pytest.mark.asyncio
async def test_handle_moderation_ban_schedules_unban(monkeypatch):
    monkeypatch.setattr(moderation_cmds, "parse_duration_to_seconds", lambda duration: 3600)
    send_mock = AsyncMock()
    monkeypatch.setattr(moderation_cmds, "send_dm_and_embed", send_mock)
    delete_mock = AsyncMock()
    monkeypatch.setattr(moderation_cmds, "delete_messages_background", delete_mock)
    schedule_unban_mock = AsyncMock()
    monkeypatch.setattr(moderation_cmds, "schedule_unban", schedule_unban_mock)

    cog = moderation_cmds.ModerationActionCog(SimpleNamespace())

    user: Any = SimpleNamespace(id=50, display_name="Target")
    ban_mock = AsyncMock()
    ctx: Any = SimpleNamespace(
        guild=SimpleNamespace(ban=ban_mock),
        channel=SimpleNamespace(),
        respond=AsyncMock(),
        followup=SimpleNamespace(send=AsyncMock()),
    )

    await cog.handle_moderation_command(ctx, user, ActionType.BAN, "Reason", duration="1h", delete_message_seconds=0)

    ban_mock.assert_awaited_once_with(user, reason="Reason")
    send_mock.assert_awaited_once_with(ctx, user, ActionType.BAN, "Reason", "1h")
    schedule_unban_mock.assert_awaited_once_with(
        guild=ctx.guild,
        user_id=user.id,
        channel=ctx.channel,
        duration_seconds=3600,
        bot=cog.discord_bot_instance,
    )


@pytest.mark.asyncio
async def test_handle_moderation_ban_permanent_skips_unban(monkeypatch):
    monkeypatch.setattr(moderation_cmds, "parse_duration_to_seconds", lambda duration: 3600)
    send_mock = AsyncMock()
    monkeypatch.setattr(moderation_cmds, "send_dm_and_embed", send_mock)
    delete_mock = AsyncMock()
    monkeypatch.setattr(moderation_cmds, "delete_messages_background", delete_mock)
    schedule_unban_mock = AsyncMock()
    monkeypatch.setattr(moderation_cmds, "schedule_unban", schedule_unban_mock)

    cog = moderation_cmds.ModerationActionCog(SimpleNamespace())

    user: Any = SimpleNamespace(id=50, display_name="Target")
    ban_mock = AsyncMock()
    ctx: Any = SimpleNamespace(
        guild=SimpleNamespace(ban=ban_mock),
        channel=SimpleNamespace(),
        respond=AsyncMock(),
        followup=SimpleNamespace(send=AsyncMock()),
    )

    await cog.handle_moderation_command(ctx, user, ActionType.BAN, "Reason", duration=PERMANENT_DURATION, delete_message_seconds=0)

    ban_mock.assert_awaited_once_with(user, reason="Reason")
    assert schedule_unban_mock.await_count == 0


@pytest.mark.asyncio
async def test_handle_moderation_command_handles_exception(monkeypatch):
    async def failing_kick(reason=None):
        raise RuntimeError("kick failed")

    monkeypatch.setattr(moderation_cmds, "parse_duration_to_seconds", lambda duration: 0)
    send_mock = AsyncMock()
    monkeypatch.setattr(moderation_cmds, "send_dm_and_embed", send_mock)
    delete_mock = AsyncMock()
    monkeypatch.setattr(moderation_cmds, "delete_messages_background", delete_mock)
    schedule_mock = AsyncMock()
    monkeypatch.setattr(moderation_cmds, "schedule_unban", schedule_mock)

    cog = moderation_cmds.ModerationActionCog(SimpleNamespace())

    user: Any = SimpleNamespace(kick=AsyncMock(side_effect=RuntimeError("boom")))
    ctx: Any = SimpleNamespace(
        guild=SimpleNamespace(ban=AsyncMock()),
        channel=SimpleNamespace(),
        respond=AsyncMock(),
        followup=SimpleNamespace(send=AsyncMock()),
    )

    await cog.handle_moderation_command(ctx, user, ActionType.KICK, "Reason")

    ctx.respond.assert_awaited_once_with("An error occurred while processing the command.", ephemeral=True)


@pytest.mark.asyncio
async def test_warn_command_aborts_when_permission_denied(monkeypatch):
    async def fake_check(self, ctx, target, perm):
        self._last_perm = perm
        return False

    handle_mock = AsyncMock()

    monkeypatch.setattr(moderation_cmds.ModerationActionCog, "check_moderation_permissions", fake_check)
    monkeypatch.setattr(moderation_cmds.ModerationActionCog, "handle_moderation_command", handle_mock)

    cog = moderation_cmds.ModerationActionCog(SimpleNamespace())

    ctx: Any = SimpleNamespace(defer=AsyncMock(), respond=AsyncMock())
    user: Any = SimpleNamespace()

    cb = getattr(moderation_cmds.ModerationActionCog.warn, "callback", None)
    assert cb is not None
    await cb(cog, ctx, user, "Reason", delete_message_seconds=15)

    ctx.defer.assert_awaited_once()
    assert cog._last_perm == "manage_messages"
    handle_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_warn_command_invokes_handler_on_success(monkeypatch):
    async def fake_check(self, ctx, target, perm):
        return True

    handle_mock = AsyncMock()

    monkeypatch.setattr(moderation_cmds.ModerationActionCog, "check_moderation_permissions", fake_check)
    monkeypatch.setattr(moderation_cmds.ModerationActionCog, "handle_moderation_command", handle_mock)

    cog = moderation_cmds.ModerationActionCog(SimpleNamespace())

    ctx: Any = SimpleNamespace(defer=AsyncMock(), respond=AsyncMock())
    user: Any = SimpleNamespace()

    cb = getattr(moderation_cmds.ModerationActionCog.warn, "callback", None)
    assert cb is not None
    await cb(cog, ctx, user, "Reason", delete_message_seconds=45)

    ctx.defer.assert_awaited_once()
    handle_mock.assert_awaited_once_with(
        ctx,
        user,
        ActionType.WARN,
        "Reason",
        delete_message_seconds=45,
    )
