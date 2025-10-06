import datetime
from types import SimpleNamespace
from typing import Iterable, cast
from unittest.mock import AsyncMock

import pytest

import discord

from modcord.util import discord_utils
from modcord.util.moderation_models import ActionData, ActionType, ModerationMessage


class DummyPermissions:
    def __init__(self, **flags) -> None:
        self.__dict__.update(flags)

    def __bool__(self) -> bool:  # pragma: no cover - convenience
        return any(self.__dict__.values())


class FakeMember:
    def __init__(self, *, member_id: int = 1, permissions: DummyPermissions | None = None, bot: bool = False) -> None:
        self.id = member_id
        self.display_name = f"member-{member_id}"
        self.mention = f"@member-{member_id}"
        self.bot = bot
        self.guild_permissions = permissions or DummyPermissions(
            administrator=False,
            manage_guild=False,
            moderate_members=False,
            ban_members=True,
            kick_members=True,
        )
        self.top_role = SimpleNamespace(position=1)
        self.sent_messages: list[str] = []
        self.timeout = AsyncMock()

    async def send(self, content: str):
        self.sent_messages.append(content)


class FakeGuild:
    def __init__(self, *, name: str = "Guild", me: object | None = None, channels: Iterable["FakeChannel"] | None = None) -> None:
        self.name = name
        self.me = me
        self.text_channels = list(channels or [])
        self.ban = AsyncMock()
        self.kick = AsyncMock()


class FakeChannel:
    def __init__(
        self,
        name: str = "channel",
        permissions: DummyPermissions | Exception | None = None,
        messages: Iterable[object] | None = None,
        history_error: str | None = None,
        fetch_error: str | None = None,
        send_error: str | None = None,
    ) -> None:
        self.name = name
        self._permissions = permissions or DummyPermissions(read_messages=True, manage_messages=True)
        self._messages = list(messages or [])
        self._history_error = history_error
        self._fetch_error = fetch_error
        self._send_error = send_error
        self.sent_embeds: list[object] = []

    def permissions_for(self, member) -> DummyPermissions:
        if isinstance(self._permissions, Exception):
            raise self._permissions
        return cast(DummyPermissions, self._permissions)

    def add_message(self, message: object) -> None:
        self._messages.append(message)

    async def history(self, limit: int = 50, after=None):  # noqa: ANN001 - signature mirrors discord
        if self._history_error == "forbidden":
            raise discord_utils.discord.Forbidden(None, "no access")
        if self._history_error == "error":
            raise RuntimeError("boom")
        for message in self._messages[:limit]:
            yield message

    async def fetch_message(self, message_id: int):
        if self._fetch_error == "forbidden":
            raise discord_utils.discord.Forbidden(None, "no access")
        if self._fetch_error == "error":
            raise RuntimeError("boom")
        for message in self._messages:
            if getattr(message, "id", None) == message_id:
                return message
        raise discord_utils.discord.NotFound(None, "not found")

    async def send(self, *, embed=None):
        if self._send_error == "forbidden":
            raise discord_utils.discord.Forbidden(None, "no access")
        if self._send_error == "error":
            raise RuntimeError("boom")
        self.sent_embeds.append(embed)


class FakeMessage:
    def __init__(self, message_id: int, guild: FakeGuild | None, author: FakeMember, channel: FakeChannel) -> None:
        self.id = message_id
        self.guild: FakeGuild | None = guild
        self.author = author
        self.channel = channel
        self.delete = AsyncMock()


@pytest.fixture(autouse=True)
def patch_discord_namespace(monkeypatch):
    class _NotFound(Exception):
        pass

    class _Forbidden(Exception):
        pass

    class _ClientUser(SimpleNamespace):
        pass

    monkeypatch.setattr(discord_utils.discord, "NotFound", _NotFound, raising=False)
    monkeypatch.setattr(discord_utils.discord, "Forbidden", _Forbidden, raising=False)
    monkeypatch.setattr(discord_utils.discord, "TextChannel", FakeChannel, raising=False)
    monkeypatch.setattr(discord_utils.discord, "Thread", FakeChannel, raising=False)
    monkeypatch.setattr(discord_utils.discord, "Member", FakeMember, raising=False)
    monkeypatch.setattr(discord_utils.discord, "ClientUser", _ClientUser, raising=False)
    monkeypatch.setattr(discord_utils.discord.utils, "utcnow", lambda: datetime.datetime.now(datetime.timezone.utc), raising=False)
    yield


def make_bot_user():
    return cast(discord.ClientUser, SimpleNamespace(name="bot", mention="@bot"))


def make_bot_client():
    return cast(discord.Client, SimpleNamespace())


def test_bot_can_manage_messages_without_bot_member():
    guild = FakeGuild(me=None)
    channel = FakeChannel()

    result = discord_utils.bot_can_manage_messages(cast(discord_utils.discord.TextChannel, channel), cast(discord_utils.discord.Guild, guild))

    assert result is True


def test_bot_can_manage_messages_permissions_exception(monkeypatch):
    guild = FakeGuild(me=FakeMember())
    channel = FakeChannel(permissions=RuntimeError("boom"))

    result = discord_utils.bot_can_manage_messages(cast(discord_utils.discord.TextChannel, channel), cast(discord_utils.discord.Guild, guild))

    assert result is False


@pytest.mark.asyncio
async def test_delete_recent_messages_zero_window_returns_zero():
    guild = FakeGuild()
    member = FakeMember()

    deleted = await discord_utils.delete_recent_messages(cast(discord_utils.discord.Guild, guild), cast(discord_utils.discord.Member, member), 0)

    assert deleted == 0


@pytest.mark.asyncio
async def test_delete_recent_messages_deletes_and_handles_errors(monkeypatch):
    member = FakeMember(member_id=5)
    good_channel = FakeChannel()
    good_channel.add_message(SimpleNamespace(id=10, author=member))
    good_channel.add_message(SimpleNamespace(id=11, author=SimpleNamespace(id=999)))
    forbidden_channel = FakeChannel(history_error="forbidden")
    error_channel = FakeChannel(history_error="error")
    guild = FakeGuild(channels=[good_channel, forbidden_channel, error_channel])

    safe_delete = AsyncMock(return_value=True)
    monkeypatch.setattr(discord_utils, "iter_moderatable_channels", lambda g: [good_channel, forbidden_channel, error_channel])
    monkeypatch.setattr(discord_utils, "safe_delete_message", safe_delete)

    deleted = await discord_utils.delete_recent_messages(cast(discord_utils.discord.Guild, guild), cast(discord_utils.discord.Member, member), 120)

    assert deleted == 1
    safe_delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_messages_by_ids_handles_invalid_and_errors(monkeypatch):
    member = FakeMember(member_id=3)
    channel = FakeChannel(messages=[SimpleNamespace(id=123, author=member)])
    forbidden_channel = FakeChannel(fetch_error="forbidden")
    error_channel = FakeChannel(fetch_error="error")
    guild = FakeGuild(channels=[channel, forbidden_channel, error_channel])

    safe_delete = AsyncMock(return_value=True)
    monkeypatch.setattr(discord_utils, "iter_moderatable_channels", lambda g: [channel, forbidden_channel, error_channel])
    monkeypatch.setattr(discord_utils, "safe_delete_message", safe_delete)

    deleted = await discord_utils.delete_messages_by_ids(cast(discord_utils.discord.Guild, guild), ["abc", "123", "999"])

    assert deleted == 1
    safe_delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_messages_by_ids_logs_missing(monkeypatch):
    channel = FakeChannel()
    guild = FakeGuild(channels=[channel])
    monkeypatch.setattr(discord_utils, "iter_moderatable_channels", lambda g: [channel])
    monkeypatch.setattr(discord_utils, "safe_delete_message", AsyncMock(return_value=False))

    deleted = await discord_utils.delete_messages_by_ids(cast(discord_utils.discord.Guild, guild), ["999"])

    assert deleted == 0


@pytest.mark.asyncio
async def test_delete_messages_background_variants(monkeypatch):
    ctx = SimpleNamespace(
        guild=FakeGuild(),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    user = FakeMember()

    delete_recent = AsyncMock(return_value=2)
    monkeypatch.setattr(discord_utils, "delete_recent_messages", delete_recent)

    await discord_utils.delete_messages_background(cast(discord_utils.discord.ApplicationContext, ctx), cast(discord_utils.discord.Member, user), 60)

    ctx.followup.send.assert_awaited_once()
    delete_recent.assert_awaited_once()

    ctx.followup.send.reset_mock()
    delete_recent.reset_mock()
    delete_recent.return_value = 0

    await discord_utils.delete_messages_background(cast(discord_utils.discord.ApplicationContext, ctx), cast(discord_utils.discord.Member, user), 60)

    ctx.followup.send.assert_awaited_once()

    ctx.followup.send.reset_mock()
    delete_recent.reset_mock()
    delete_recent.side_effect = RuntimeError("failure")

    await discord_utils.delete_messages_background(cast(discord_utils.discord.ApplicationContext, ctx), cast(discord_utils.discord.Member, user), 60)

    ctx.followup.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_safe_delete_message_variants(monkeypatch):
    message = FakeMessage(1, FakeGuild(), FakeMember(), FakeChannel())

    result_success = await discord_utils.safe_delete_message(cast(discord_utils.discord.Message, message))
    assert result_success is True
    message.delete.assert_awaited_once()

    message_not_found = FakeMessage(2, FakeGuild(), FakeMember(), FakeChannel())
    async def _raise_not_found():
        raise discord_utils.discord.NotFound(None, "gone")
    message_not_found.delete.side_effect = _raise_not_found
    result_not_found = await discord_utils.safe_delete_message(cast(discord_utils.discord.Message, message_not_found))
    assert result_not_found is False

    message_forbidden = FakeMessage(3, FakeGuild(), FakeMember(), FakeChannel())
    async def _raise_forbidden():
        raise discord_utils.discord.Forbidden(None, "no access")
    message_forbidden.delete.side_effect = _raise_forbidden
    result_forbidden = await discord_utils.safe_delete_message(cast(discord_utils.discord.Message, message_forbidden))
    assert result_forbidden is False

    message_error = FakeMessage(4, FakeGuild(), FakeMember(), FakeChannel())
    async def _raise_error():
        raise RuntimeError("boom")
    message_error.delete.side_effect = _raise_error
    result_error = await discord_utils.safe_delete_message(cast(discord_utils.discord.Message, message_error))
    assert result_error is False


@pytest.mark.asyncio
async def test_send_dm_to_user_variants(monkeypatch):
    member = FakeMember()
    result_success = await discord_utils.send_dm_to_user(cast(discord_utils.discord.Member, member), "Hi")
    assert result_success is True
    assert member.sent_messages == ["Hi"]

    member_forbidden = FakeMember()
    async def _raise_forbidden(content):
        raise discord_utils.discord.Forbidden(None, "no access")
    member_forbidden.send = _raise_forbidden  # type: ignore[assignment]
    result_forbidden = await discord_utils.send_dm_to_user(cast(discord_utils.discord.Member, member_forbidden), "Hi")
    assert result_forbidden is False

    member_error = FakeMember()
    async def _raise_error(content):
        raise RuntimeError("boom")
    member_error.send = _raise_error  # type: ignore[assignment]
    result_error = await discord_utils.send_dm_to_user(cast(discord_utils.discord.Member, member_error), "Hi")
    assert result_error is False


@pytest.mark.asyncio
async def test_send_dm_and_embed_uses_fallback(monkeypatch):
    ctx = SimpleNamespace(
        guild=FakeGuild(name="Guild"),
        bot=SimpleNamespace(user=SimpleNamespace(name="Bot")),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    user = FakeMember()

    send_dm = AsyncMock()
    create_embed = AsyncMock(return_value="EMBED")
    monkeypatch.setattr(discord_utils, "send_dm_to_user", send_dm)
    monkeypatch.setattr(discord_utils, "create_punishment_embed", create_embed)

    await discord_utils.send_dm_and_embed(
        cast(discord_utils.discord.ApplicationContext, ctx),
        cast(discord_utils.discord.Member, user),
        ActionType.DELETE,
        "Reason",
    )

    send_dm.assert_awaited_once()
    await_args = send_dm.await_args
    assert await_args is not None
    fallback_message = await_args.args[1]
    assert "delete" in fallback_message.lower()
    create_embed.assert_awaited_once()
    ctx.followup.send.assert_awaited_once_with(embed="EMBED")


def test_has_permissions_returns_false_for_non_member():
    ctx = SimpleNamespace(author=SimpleNamespace())
    assert discord_utils.has_permissions(cast(discord_utils.discord.ApplicationContext, ctx), ban_members=True) is False


@pytest.mark.asyncio
async def test_apply_action_decision_returns_false_without_discord_message():
    action = ActionData(user_id="1", action=ActionType.BAN, reason="R", message_ids=[])
    pivot = ModerationMessage(
        message_id="1",
        user_id="1",
        username="user",
        content="txt",
        timestamp="2024-01-01T00:00:00Z",
        guild_id=1,
        channel_id=1,
        discord_message=None,
    )

    bot_user = make_bot_user()
    bot_client = make_bot_client()

    result = await discord_utils.apply_action_decision(action, pivot, bot_user, bot_client)

    assert result is False


@pytest.mark.asyncio
async def test_apply_action_decision_skips_when_guild_missing():
    member = FakeMember()
    channel = FakeChannel()
    guild = FakeGuild()
    message = FakeMessage(10, None, member, channel)
    action = ActionData(user_id=str(member.id), action=ActionType.KICK, reason="R", message_ids=[])
    pivot = ModerationMessage(
        message_id=str(message.id),
        user_id=str(member.id),
        username="user",
        content="txt",
        timestamp="2024-01-01T00:00:00Z",
        guild_id=1,
        channel_id=1,
        discord_message=cast(discord_utils.discord.Message, message),
    )

    bot_user = make_bot_user()
    bot_client = make_bot_client()

    result = await discord_utils.apply_action_decision(action, pivot, bot_user, bot_client)

    assert result is False


@pytest.mark.asyncio
async def test_apply_action_decision_schedule_unban_failure(monkeypatch):
    member = FakeMember()
    channel = FakeChannel()
    guild = FakeGuild(me=SimpleNamespace(guild_permissions=DummyPermissions(ban_members=True, moderate_members=True)))
    message = FakeMessage(20, guild, member, channel)
    action = ActionData(
        user_id=str(member.id),
        action=ActionType.BAN,
        reason="R",
        message_ids=[str(message.id)],
        ban_duration=3600,
    )
    pivot = ModerationMessage(
        message_id=str(message.id),
        user_id=str(member.id),
        username="user",
        content="txt",
        timestamp="2024-01-01T00:00:00Z",
        guild_id=1,
        channel_id=1,
        discord_message=cast(discord_utils.discord.Message, message),
    )

    monkeypatch.setattr(discord_utils, "safe_delete_message", AsyncMock(return_value=True))
    monkeypatch.setattr(discord_utils, "delete_messages_by_ids", AsyncMock(return_value=0))
    monkeypatch.setattr(discord_utils, "send_dm_to_user", AsyncMock(return_value=True))
    monkeypatch.setattr(discord_utils, "create_punishment_embed", AsyncMock(return_value="EMBED"))
    monkeypatch.setattr(discord_utils, "schedule_unban", AsyncMock(side_effect=RuntimeError("fail")))

    bot_user = make_bot_user()
    bot_client = make_bot_client()

    result = await discord_utils.apply_action_decision(action, pivot, bot_user, bot_client)

    assert result is False
    assert channel.sent_embeds == ["EMBED"]


@pytest.mark.asyncio
async def test_apply_action_decision_channel_send_failure(monkeypatch):
    member = FakeMember()
    channel = FakeChannel(send_error="forbidden")
    guild = FakeGuild()
    message = FakeMessage(30, guild, member, channel)
    action = ActionData(user_id=str(member.id), action=ActionType.WARN, reason="R", message_ids=[])
    pivot = ModerationMessage(
        message_id=str(message.id),
        user_id=str(member.id),
        username="user",
        content="txt",
        timestamp="2024-01-01T00:00:00Z",
        guild_id=1,
        channel_id=1,
        discord_message=cast(discord_utils.discord.Message, message),
    )

    monkeypatch.setattr(discord_utils, "safe_delete_message", AsyncMock(return_value=True))
    monkeypatch.setattr(discord_utils, "delete_messages_by_ids", AsyncMock(return_value=0))
    monkeypatch.setattr(discord_utils, "send_dm_to_user", AsyncMock(return_value=True))
    monkeypatch.setattr(discord_utils, "create_punishment_embed", AsyncMock(return_value="EMBED"))

    bot_user = make_bot_user()
    bot_client = make_bot_client()

    result = await discord_utils.apply_action_decision(action, pivot, bot_user, bot_client)

    assert result is True
    assert channel.sent_embeds == []


@pytest.mark.asyncio
async def test_delete_recent_messages_by_count_handles_edge_cases(monkeypatch):
    guild = FakeGuild()
    member = FakeMember()

    zero = await discord_utils.delete_recent_messages_by_count(cast(discord_utils.discord.Guild, guild), cast(discord_utils.discord.Member, member), 0)
    assert zero == 0

    channel = FakeChannel(messages=[SimpleNamespace(author=member, id=1), SimpleNamespace(author=member, id=2)])
    forbidden_channel = FakeChannel(history_error="forbidden")
    error_channel = FakeChannel(history_error="error")
    guild = FakeGuild(channels=[channel, forbidden_channel, error_channel])

    monkeypatch.setattr(discord_utils, "iter_moderatable_channels", lambda g: [channel, forbidden_channel, error_channel])
    monkeypatch.setattr(discord_utils, "safe_delete_message", AsyncMock(return_value=True))

    deleted = await discord_utils.delete_recent_messages_by_count(cast(discord_utils.discord.Guild, guild), cast(discord_utils.discord.Member, member), 2)

    assert deleted == 2

