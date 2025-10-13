import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest

from modcord.util import discord_utils
from modcord.util.moderation_datatypes import ActionType


class FakePermissions:
    def __init__(self, **flags) -> None:
        self.__dict__.update(flags)


class FakeChannel:
    def __init__(self, name: str, permissions: FakePermissions | None = None) -> None:
        self.name = name
        self._permissions = permissions or FakePermissions(read_messages=True, manage_messages=True)
        self._messages = {}

    def permissions_for(self, member):
        return self._permissions

    def add_message(self, message_id: int, message):
        self._messages[message_id] = message

    async def fetch_message(self, message_id: int):
        if message_id not in self._messages:
            raise discord_utils.discord.NotFound(None, "not found")
        return self._messages[message_id]

    async def history(self, limit: int = 50, after=None):
        for message in list(self._messages.values())[:limit]:
            yield message


class FakeGuild:
    def __init__(self, channels: list[FakeChannel], member_permissions: FakePermissions | None = None) -> None:
        self.text_channels = channels
        self.me = SimpleNamespace(guild_permissions=member_permissions or FakePermissions(read_messages=True, manage_messages=True))


class FakeMember:
    def __init__(self, *, admin: bool = False) -> None:
        self.id = 1
        self.display_name = "member"
        self.mention = "@member"
        self.bot = False
        self.guild_permissions = SimpleNamespace(
            administrator=admin,
            manage_guild=admin,
            moderate_members=admin,
            ban_members=admin,
            kick_members=admin,
        )
        self.top_role = SimpleNamespace(position=1)


class FakeContext(SimpleNamespace):
    pass


@pytest.fixture(autouse=True)
def patch_discord_exceptions(monkeypatch):
    class _NotFound(Exception):
        def __init__(self, *args, **kwargs):
            super().__init__(*args)

    class _Forbidden(Exception):
        def __init__(self, *args, **kwargs):
            super().__init__(*args)

    monkeypatch.setattr(discord_utils.discord, "NotFound", _NotFound, raising=False)
    monkeypatch.setattr(discord_utils.discord, "Forbidden", _Forbidden, raising=False)
    monkeypatch.setattr(discord_utils.discord, "TextChannel", FakeChannel, raising=False)
    monkeypatch.setattr(discord_utils.discord, "Guild", FakeGuild, raising=False)
    monkeypatch.setattr(discord_utils.discord, "Member", FakeMember, raising=False)
    monkeypatch.setattr(discord_utils.discord, "ApplicationContext", FakeContext, raising=False)


def test_bot_can_manage_messages_requires_permissions():
    guild = FakeGuild([])
    channel = FakeChannel("general", permissions=FakePermissions(read_messages=True, manage_messages=False))
    assert discord_utils.bot_can_manage_messages(
        cast(discord_utils.discord.TextChannel, channel),
        cast(discord_utils.discord.Guild, guild),
    ) is False

    channel_allowed = FakeChannel("allowed")
    assert discord_utils.bot_can_manage_messages(
        cast(discord_utils.discord.TextChannel, channel_allowed),
        cast(discord_utils.discord.Guild, guild),
    ) is True


def test_iter_moderatable_channels_filters(monkeypatch):
    guild = FakeGuild([
        FakeChannel("general", permissions=FakePermissions(read_messages=True, manage_messages=True)),
        FakeChannel("restricted", permissions=FakePermissions(read_messages=False, manage_messages=False)),
    ])

    channels = list(discord_utils.iter_moderatable_channels(cast(discord_utils.discord.Guild, guild)))

    assert len(channels) == 1
    assert channels[0].name == "general"


def test_has_elevated_permissions_detects_admin():
    member = FakeMember(admin=True)
    assert discord_utils.has_elevated_permissions(cast(discord_utils.discord.Member, member)) is True

    non_admin = FakeMember(admin=False)
    assert discord_utils.has_elevated_permissions(cast(discord_utils.discord.Member, non_admin)) is False


@pytest.mark.asyncio
async def test_send_dm_to_user_handles_forbidden(monkeypatch):
    class FakeDmMember(FakeMember):
        def __init__(self) -> None:
            super().__init__()
            self.display_name = "User"
            self.sent: list[str] = []

        async def send(self, content):
            raise discord_utils.discord.Forbidden(None, "forbidden")

    user = FakeDmMember()

    success = await discord_utils.send_dm_to_user(cast(discord_utils.discord.Member, user), "Hello")

    assert success is False


@pytest.mark.asyncio
async def test_send_dm_and_embed_uses_followup(monkeypatch):
    user = FakeMember()
    dm_mock = AsyncMock(return_value=True)
    embed_mock = AsyncMock(return_value="embed")
    followup_send = AsyncMock()
    ctx = FakeContext(
        guild=SimpleNamespace(name="Guild"),
        bot=SimpleNamespace(user=SimpleNamespace(name="Bot")),
        followup=SimpleNamespace(send=followup_send),
    )

    monkeypatch.setattr(discord_utils, "create_punishment_embed", embed_mock)
    monkeypatch.setattr(discord_utils, "send_dm_to_user", dm_mock)

    await discord_utils.send_dm_and_embed(
        cast(discord_utils.discord.ApplicationContext, ctx),
        cast(discord_utils.discord.Member, user),
        ActionType.WARN,
        "Reason",
    )

    dm_mock.assert_awaited_once()
    followup_send.assert_awaited_once_with(embed="embed")


def test_has_permissions_checks_author(monkeypatch):
    ctx = FakeContext(
        author=FakeMember(),
    )

    ctx.author.guild_permissions.ban_members = True
    ctx.author.guild_permissions.kick_members = False
    assert discord_utils.has_permissions(cast(discord_utils.discord.ApplicationContext, ctx), ban_members=True) is True
    assert (
        discord_utils.has_permissions(
            cast(discord_utils.discord.ApplicationContext, ctx),
            ban_members=True,
            kick_members=True,
        )
        is False
    )


@pytest.mark.asyncio
async def test_delete_messages_by_ids_deletes(monkeypatch):
    channel = FakeChannel("general")
    message = SimpleNamespace(id=101)
    channel.add_message(101, message)
    guild = FakeGuild([channel])

    delete_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(discord_utils, "safe_delete_message", delete_mock)
    monkeypatch.setattr(discord_utils, "iter_moderatable_channels", lambda g: [channel])

    deleted = await discord_utils.delete_messages_by_ids(
        cast(discord_utils.discord.Guild, guild),
        ["101", "202"],
    )

    assert deleted == 1
    delete_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_recent_messages_by_count_limits(monkeypatch):
    channel = FakeChannel("general")
    member = FakeMember()
    channel.add_message(1, SimpleNamespace(author=member))
    channel.add_message(2, SimpleNamespace(author=member))
    guild = FakeGuild([channel])

    delete_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(discord_utils, "safe_delete_message", delete_mock)
    monkeypatch.setattr(discord_utils, "iter_moderatable_channels", lambda g: [channel])

    count = await discord_utils.delete_recent_messages_by_count(
        cast(discord_utils.discord.Guild, guild),
        cast(discord_utils.discord.Member, member),
        1,
    )

    assert count == 1
    delete_mock.assert_awaited()


@pytest.mark.asyncio
async def test_delete_messages_background_reports(monkeypatch):
    ctx = FakeContext(
        guild=SimpleNamespace(id=1),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    user = FakeMember()

    delete_mock = AsyncMock(return_value=2)
    monkeypatch.setattr(discord_utils, "delete_recent_messages", delete_mock)

    await discord_utils.delete_messages_background(
        cast(discord_utils.discord.ApplicationContext, ctx),
        cast(discord_utils.discord.Member, user),
        60,
    )

    ctx.followup.send.assert_awaited_once()