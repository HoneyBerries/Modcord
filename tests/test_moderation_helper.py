import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest

from modcord.util import moderation_helper
from modcord.util.moderation_models import ActionData, ActionType, ModerationBatch, ModerationMessage


class FakePermissions:
    def __init__(self, **flags) -> None:
        self.__dict__.update(flags)


class FakeRole:
    def __init__(self, position: int) -> None:
        self.position = position

    def __ge__(self, other: "FakeRole") -> bool:
        return self.position >= other.position


class FakeMember:
    def __init__(self, *, member_id: int, is_bot: bool = False, guild_permissions: FakePermissions | None = None, top_role: FakeRole | None = None) -> None:
        self.id = member_id
        self.bot = is_bot
        self.guild_permissions = guild_permissions or FakePermissions(
            ban_members=True,
            kick_members=True,
            moderate_members=True,
        )
        self.top_role = top_role or FakeRole(10)
        self.display_name = f"member-{member_id}"
        self.mention = f"@member-{member_id}"


class FakeBotMember(FakeMember):
    def __init__(self, *, guild_permissions=None, top_role=None) -> None:
        super().__init__(member_id=999, guild_permissions=guild_permissions, top_role=top_role)


class FakeGuild:
    def __init__(self, guild_id: int, *, owner_id: int = 1, me: FakeBotMember | None = None) -> None:
        self.id = guild_id
        self.owner_id = owner_id
        self.me = me or FakeBotMember(top_role=FakeRole(5))


class FakeChannel:
    def __init__(self, channel_id: int, guild: FakeGuild) -> None:
        self.id = channel_id
        self.guild = guild
        self.name = f"channel-{channel_id}"

    def permissions_for(self, member: FakeMember) -> FakePermissions:
        return member.guild_permissions


class FakeMessage:
    def __init__(self, message_id: int, guild: FakeGuild, author: FakeMember, channel: object) -> None:
        self.id = message_id
        self.guild = guild
        self.author = author
        self.channel = channel


@pytest.fixture(autouse=True)
def patch_discord_types(monkeypatch):
    monkeypatch.setattr(moderation_helper.discord, "Message", FakeMessage, raising=False)
    monkeypatch.setattr(moderation_helper.discord, "Member", FakeMember, raising=False)
    monkeypatch.setattr(moderation_helper.discord, "TextChannel", FakeChannel, raising=False)
    monkeypatch.setattr(moderation_helper.discord, "Thread", SimpleNamespace, raising=False)
    yield


@pytest.fixture
def fake_settings(monkeypatch):
    settings = SimpleNamespace(
        get_server_rules=lambda guild_id: "Be kind",
        is_ai_enabled=lambda guild_id: True,
        is_action_allowed=lambda guild_id, action: True,
        add_message_to_history=AsyncMock(),
    )
    monkeypatch.setattr(moderation_helper, "guild_settings_manager", settings)
    return settings


@pytest.mark.asyncio
async def test_process_message_batch_calls_apply(monkeypatch, fake_settings):
    batch = ModerationBatch(channel_id=123)
    guild = FakeGuild(guild_id=55)
    author = FakeMember(member_id=42)
    channel = FakeChannel(channel_id=123, guild=guild)
    discord_message = FakeMessage(message_id=1, guild=guild, author=author, channel=channel)
    batch.add_message(
        ModerationMessage(
            message_id="1",
            user_id="42",
            username="member",
            content="hello",
            timestamp="2024-01-01T00:00:00Z",
            guild_id=guild.id,
            channel_id=channel.id,
                discord_message=cast(moderation_helper.discord.Message, discord_message),
        )
    )

    actions = [ActionData("42", ActionType.BAN, "Reason", ["1", "missing"])]

    apply_mock = AsyncMock(return_value=True)
    processor_mock = AsyncMock(return_value=actions)
    monkeypatch.setattr(moderation_helper.moderation_processor, "get_batch_moderation_actions", processor_mock)
    monkeypatch.setattr(moderation_helper, "apply_batch_action", apply_mock)
    monkeypatch.setattr(moderation_helper.discord_utils, "apply_action_decision", AsyncMock(return_value=True))

    self_obj = SimpleNamespace(bot=SimpleNamespace(user=object()))

    original_available = moderation_helper.model_state.available
    original_error = moderation_helper.model_state.init_error
    try:
        moderation_helper.model_state.available = True
        moderation_helper.model_state.init_error = None

        await moderation_helper.process_message_batch(self_obj, batch)
    finally:
        moderation_helper.model_state.available = original_available
        moderation_helper.model_state.init_error = original_error

    processor_mock.assert_awaited_once()
    apply_mock.assert_awaited_once()
    apply_args = apply_mock.await_args
    assert apply_args is not None
    _, forwarded_action, _ = apply_args.args
    assert forwarded_action.message_ids == ["1"]


@pytest.mark.asyncio
async def test_apply_batch_action_filters_invalid_messages(monkeypatch, fake_settings):
    guild = FakeGuild(guild_id=12, me=FakeBotMember(top_role=FakeRole(20)))
    author = FakeMember(member_id=10, guild_permissions=FakePermissions(
        ban_members=True,
        kick_members=True,
        moderate_members=True,
    ), top_role=FakeRole(1))
    channel = FakeChannel(channel_id=99, guild=guild)
    discord_message = FakeMessage(message_id=5, guild=guild, author=author, channel=channel)

    batch = ModerationBatch(channel_id=99)
    batch.add_message(
        ModerationMessage(
            message_id="5",
            user_id="10",
            username="user",
            content="bad",
            timestamp="2024-01-01T00:00:00Z",
            guild_id=guild.id,
            channel_id=channel.id,
                discord_message=cast(moderation_helper.discord.Message, discord_message),
        )
    )

    action = ActionData("10", ActionType.BAN, "Reason", ["5", "missing"], ban_duration=None)

    monkeypatch.setattr(moderation_helper.discord_utils, "has_elevated_permissions", lambda member: False)
    monkeypatch.setattr(moderation_helper.discord_utils, "bot_can_manage_messages", lambda channel, g: True)
    apply_decision = AsyncMock(return_value=True)
    monkeypatch.setattr(moderation_helper.discord_utils, "apply_action_decision", apply_decision)

    self_obj = SimpleNamespace(bot=SimpleNamespace(user=object()))

    result = await moderation_helper.apply_batch_action(self_obj, action, batch)

    assert result is True
    apply_decision.assert_awaited_once()
    await_args = apply_decision.await_args
    assert await_args is not None
    called_action = await_args.kwargs["action"]
    assert called_action.message_ids == ["5", "missing"]


@pytest.mark.asyncio
async def test_apply_batch_action_respects_disabled_permission(monkeypatch, fake_settings):
    guild = FakeGuild(guild_id=14, me=FakeBotMember(guild_permissions=FakePermissions(ban_members=False, kick_members=False, moderate_members=False), top_role=FakeRole(5)))
    author = FakeMember(member_id=50, guild_permissions=FakePermissions(ban_members=True, kick_members=True, moderate_members=True), top_role=FakeRole(1))
    channel = FakeChannel(channel_id=11, guild=guild)
    discord_message = FakeMessage(message_id=9, guild=guild, author=author, channel=channel)

    batch = ModerationBatch(channel_id=11)
    batch.add_message(
        ModerationMessage(
            message_id="9",
            user_id="50",
            username="user",
            content="policy",
            timestamp="2024-01-01T00:00:00Z",
            guild_id=guild.id,
            channel_id=channel.id,
                discord_message=cast(moderation_helper.discord.Message, discord_message),
        )
    )

    action = ActionData("50", ActionType.BAN, "Reason", ["9"], ban_duration=None)

    monkeypatch.setattr(moderation_helper.discord_utils, "has_elevated_permissions", lambda member: False)

    result = await moderation_helper.apply_batch_action(SimpleNamespace(bot=SimpleNamespace(user=object())), action, batch)

    assert result is False


@pytest.mark.asyncio
async def test_process_message_batch_skips_empty(monkeypatch, fake_settings):
    batch = ModerationBatch(channel_id=77)
    processor_mock = AsyncMock()
    monkeypatch.setattr(moderation_helper.moderation_processor, "get_batch_moderation_actions", processor_mock)

    await moderation_helper.process_message_batch(SimpleNamespace(bot=SimpleNamespace(user=object())), batch)

    processor_mock.assert_not_called()


@pytest.mark.asyncio
async def test_process_message_batch_skips_when_ai_disabled(monkeypatch, fake_settings):
    batch = ModerationBatch(channel_id=88)
    guild = FakeGuild(guild_id=101)
    author = FakeMember(member_id=20)
    channel = FakeChannel(channel_id=88, guild=guild)
    discord_message = FakeMessage(message_id=1, guild=guild, author=author, channel=channel)
    batch.add_message(
        ModerationMessage(
            message_id="1",
            user_id=str(author.id),
            username="user",
            content="msg",
            timestamp="2024-01-01T00:00:00Z",
            guild_id=guild.id,
            channel_id=channel.id,
            discord_message=cast(moderation_helper.discord.Message, discord_message),
        )
    )

    processor_mock = AsyncMock()
    monkeypatch.setattr(moderation_helper.moderation_processor, "get_batch_moderation_actions", processor_mock)
    fake_settings.is_ai_enabled = lambda guild_id: False

    await moderation_helper.process_message_batch(SimpleNamespace(bot=SimpleNamespace(user=object())), batch)

    processor_mock.assert_not_called()


@pytest.mark.asyncio
async def test_process_message_batch_skips_when_model_unavailable(monkeypatch, fake_settings):
    batch = ModerationBatch(channel_id=90)
    guild = FakeGuild(guild_id=202)
    author = FakeMember(member_id=30)
    channel = FakeChannel(channel_id=90, guild=guild)
    discord_message = FakeMessage(message_id=9, guild=guild, author=author, channel=channel)
    batch.add_message(
        ModerationMessage(
            message_id="9",
            user_id=str(author.id),
            username="user",
            content="msg",
            timestamp="2024-01-01T00:00:00Z",
            guild_id=guild.id,
            channel_id=channel.id,
            discord_message=cast(moderation_helper.discord.Message, discord_message),
        )
    )

    processor_mock = AsyncMock()
    monkeypatch.setattr(moderation_helper.moderation_processor, "get_batch_moderation_actions", processor_mock)

    original_available = moderation_helper.model_state.available
    original_error = moderation_helper.model_state.init_error
    try:
        moderation_helper.model_state.available = False
        moderation_helper.model_state.init_error = "unavailable"

        await moderation_helper.process_message_batch(SimpleNamespace(bot=SimpleNamespace(user=object())), batch)
    finally:
        moderation_helper.model_state.available = original_available
        moderation_helper.model_state.init_error = original_error

    processor_mock.assert_not_called()


@pytest.mark.asyncio
async def test_apply_batch_action_returns_false_for_null_action():
    batch = ModerationBatch(channel_id=11)
    action = ActionData("5", ActionType.NULL, "Reason", [])

    result = await moderation_helper.apply_batch_action(SimpleNamespace(bot=SimpleNamespace(user=object())), action, batch)

    assert result is False


@pytest.mark.asyncio
async def test_apply_batch_action_returns_false_without_user_messages(monkeypatch, fake_settings):
    guild = FakeGuild(guild_id=12)
    author = FakeMember(member_id=22)
    channel = FakeChannel(channel_id=12, guild=guild)
    discord_message = FakeMessage(message_id=2, guild=guild, author=author, channel=channel)
    batch = ModerationBatch(channel_id=12)
    batch.add_message(
        ModerationMessage(
            message_id="2",
            user_id="99",
            username="someone",
            content="hello",
            timestamp="2024-01-01T00:00:00Z",
            guild_id=guild.id,
            channel_id=channel.id,
            discord_message=cast(moderation_helper.discord.Message, discord_message),
        )
    )

    action = ActionData("5", ActionType.BAN, "Reason", [])

    result = await moderation_helper.apply_batch_action(SimpleNamespace(bot=SimpleNamespace(user=object())), action, batch)

    assert result is False


@pytest.mark.asyncio
async def test_apply_batch_action_returns_false_without_discord_message(monkeypatch, fake_settings):
    guild = FakeGuild(guild_id=14)
    batch = ModerationBatch(channel_id=14)
    batch.add_message(
        ModerationMessage(
            message_id="7",
            user_id="42",
            username="user",
            content="hello",
            timestamp="2024-01-01T00:00:00Z",
            guild_id=guild.id,
            channel_id=14,
            discord_message=None,
        )
    )

    action = ActionData("42", ActionType.BAN, "Reason", [])

    result = await moderation_helper.apply_batch_action(SimpleNamespace(bot=SimpleNamespace(user=object())), action, batch)

    assert result is False


@pytest.mark.asyncio
async def test_apply_batch_action_respects_guild_setting(monkeypatch, fake_settings):
    guild = FakeGuild(guild_id=16)
    author = FakeMember(member_id=16)
    channel = FakeChannel(channel_id=16, guild=guild)
    discord_message = FakeMessage(message_id=4, guild=guild, author=author, channel=channel)
    batch = ModerationBatch(channel_id=16)
    batch.add_message(
        ModerationMessage(
            message_id="4",
            user_id=str(author.id),
            username="user",
            content="hi",
            timestamp="2024-01-01T00:00:00Z",
            guild_id=guild.id,
            channel_id=channel.id,
            discord_message=cast(moderation_helper.discord.Message, discord_message),
        )
    )

    fake_settings.is_action_allowed = lambda guild_id, action: False
    action = ActionData(str(author.id), ActionType.BAN, "Reason", [])

    result = await moderation_helper.apply_batch_action(SimpleNamespace(bot=SimpleNamespace(user=object())), action, batch)

    assert result is False


@pytest.mark.asyncio
async def test_apply_batch_action_skips_guild_owner(monkeypatch, fake_settings):
    owner_id = 77
    guild = FakeGuild(guild_id=18, owner_id=owner_id)
    author = FakeMember(member_id=owner_id)
    channel = FakeChannel(channel_id=18, guild=guild)
    discord_message = FakeMessage(message_id=8, guild=guild, author=author, channel=channel)
    batch = ModerationBatch(channel_id=18)
    batch.add_message(
        ModerationMessage(
            message_id="8",
            user_id=str(author.id),
            username="owner",
            content="hello",
            timestamp="2024-01-01T00:00:00Z",
            guild_id=guild.id,
            channel_id=channel.id,
            discord_message=cast(moderation_helper.discord.Message, discord_message),
        )
    )

    action = ActionData(str(author.id), ActionType.BAN, "Reason", [])

    result = await moderation_helper.apply_batch_action(SimpleNamespace(bot=SimpleNamespace(user=object())), action, batch)

    assert result is False


@pytest.mark.asyncio
async def test_apply_batch_action_skips_elevated_permissions(monkeypatch, fake_settings):
    guild = FakeGuild(guild_id=20)
    author = FakeMember(member_id=33)
    channel = FakeChannel(channel_id=20, guild=guild)
    discord_message = FakeMessage(message_id=9, guild=guild, author=author, channel=channel)
    batch = ModerationBatch(channel_id=20)
    batch.add_message(
        ModerationMessage(
            message_id="9",
            user_id=str(author.id),
            username="mod",
            content="hello",
            timestamp="2024-01-01T00:00:00Z",
            guild_id=guild.id,
            channel_id=channel.id,
            discord_message=cast(moderation_helper.discord.Message, discord_message),
        )
    )

    monkeypatch.setattr(moderation_helper.discord_utils, "has_elevated_permissions", lambda member: True)
    action = ActionData(str(author.id), ActionType.KICK, "Reason", [])

    result = await moderation_helper.apply_batch_action(SimpleNamespace(bot=SimpleNamespace(user=object())), action, batch)

    assert result is False


@pytest.mark.asyncio
async def test_apply_batch_action_skips_when_target_role_higher(monkeypatch, fake_settings):
    guild = FakeGuild(guild_id=22, me=FakeBotMember(top_role=FakeRole(2)))
    author = FakeMember(member_id=35, top_role=FakeRole(5))
    channel = FakeChannel(channel_id=22, guild=guild)
    discord_message = FakeMessage(message_id=11, guild=guild, author=author, channel=channel)
    batch = ModerationBatch(channel_id=22)
    batch.add_message(
        ModerationMessage(
            message_id="11",
            user_id=str(author.id),
            username="higher",
            content="hello",
            timestamp="2024-01-01T00:00:00Z",
            guild_id=guild.id,
            channel_id=channel.id,
            discord_message=cast(moderation_helper.discord.Message, discord_message),
        )
    )

    monkeypatch.setattr(moderation_helper.discord_utils, "has_elevated_permissions", lambda member: False)
    action = ActionData(str(author.id), ActionType.WARN, "Reason", [])

    result = await moderation_helper.apply_batch_action(SimpleNamespace(bot=SimpleNamespace(user=object())), action, batch)

    assert result is False


@pytest.mark.asyncio
async def test_apply_batch_action_requires_ban_permission(monkeypatch, fake_settings):
    guild = FakeGuild(guild_id=24, me=FakeBotMember(guild_permissions=FakePermissions(ban_members=False, kick_members=True, moderate_members=True)))
    author = FakeMember(member_id=36)
    channel = FakeChannel(channel_id=24, guild=guild)
    discord_message = FakeMessage(message_id=12, guild=guild, author=author, channel=channel)
    batch = ModerationBatch(channel_id=24)
    batch.add_message(
        ModerationMessage(
            message_id="12",
            user_id=str(author.id),
            username="user",
            content="hello",
            timestamp="2024-01-01T00:00:00Z",
            guild_id=guild.id,
            channel_id=channel.id,
            discord_message=cast(moderation_helper.discord.Message, discord_message),
        )
    )

    monkeypatch.setattr(moderation_helper.discord_utils, "has_elevated_permissions", lambda member: False)
    action = ActionData(str(author.id), ActionType.BAN, "Reason", [])

    result = await moderation_helper.apply_batch_action(SimpleNamespace(bot=SimpleNamespace(user=object())), action, batch)

    assert result is False


@pytest.mark.asyncio
async def test_apply_batch_action_delete_requires_supported_channel(monkeypatch, fake_settings):
    guild = FakeGuild(guild_id=26)
    author = FakeMember(member_id=38)
    channel = FakeChannel(channel_id=26, guild=guild)
    discord_message = FakeMessage(message_id=13, guild=guild, author=author, channel=channel)
    discord_message.channel = SimpleNamespace(name="voice-channel")
    batch = ModerationBatch(channel_id=26)
    batch.add_message(
        ModerationMessage(
            message_id="13",
            user_id=str(author.id),
            username="user",
            content="hello",
            timestamp="2024-01-01T00:00:00Z",
            guild_id=guild.id,
            channel_id=channel.id,
            discord_message=cast(moderation_helper.discord.Message, discord_message),
        )
    )

    monkeypatch.setattr(moderation_helper.discord_utils, "has_elevated_permissions", lambda member: False)
    action = ActionData(str(author.id), ActionType.DELETE, "Reason", [])

    result = await moderation_helper.apply_batch_action(SimpleNamespace(bot=SimpleNamespace(user=object())), action, batch)

    assert result is False


@pytest.mark.asyncio
async def test_apply_batch_action_delete_requires_manage_messages(monkeypatch, fake_settings):
    guild = FakeGuild(guild_id=28)
    author = FakeMember(member_id=40)
    channel = FakeChannel(channel_id=28, guild=guild)
    discord_message = FakeMessage(message_id=14, guild=guild, author=author, channel=channel)
    batch = ModerationBatch(channel_id=28)
    batch.add_message(
        ModerationMessage(
            message_id="14",
            user_id=str(author.id),
            username="user",
            content="hello",
            timestamp="2024-01-01T00:00:00Z",
            guild_id=guild.id,
            channel_id=channel.id,
            discord_message=cast(moderation_helper.discord.Message, discord_message),
        )
    )

    monkeypatch.setattr(moderation_helper.discord_utils, "has_elevated_permissions", lambda member: False)
    monkeypatch.setattr(moderation_helper.discord_utils, "bot_can_manage_messages", lambda channel, g: False)
    action = ActionData(str(author.id), ActionType.DELETE, "Reason", [])

    result = await moderation_helper.apply_batch_action(SimpleNamespace(bot=SimpleNamespace(user=object())), action, batch)

    assert result is False


@pytest.mark.asyncio
async def test_apply_batch_action_returns_false_on_apply_exception(monkeypatch, fake_settings):
    guild = FakeGuild(guild_id=30)
    author = FakeMember(member_id=44)
    channel = FakeChannel(channel_id=30, guild=guild)
    discord_message = FakeMessage(message_id=15, guild=guild, author=author, channel=channel)
    batch = ModerationBatch(channel_id=30)
    batch.add_message(
        ModerationMessage(
            message_id="15",
            user_id=str(author.id),
            username="user",
            content="hello",
            timestamp="2024-01-01T00:00:00Z",
            guild_id=guild.id,
            channel_id=channel.id,
            discord_message=cast(moderation_helper.discord.Message, discord_message),
        )
    )

    monkeypatch.setattr(moderation_helper.discord_utils, "has_elevated_permissions", lambda member: False)
    monkeypatch.setattr(moderation_helper.discord_utils, "apply_action_decision", AsyncMock(side_effect=RuntimeError("boom")))
    action = ActionData(str(author.id), ActionType.WARN, "Reason", [])

    result = await moderation_helper.apply_batch_action(SimpleNamespace(bot=SimpleNamespace(user=object())), action, batch)

    assert result is False


@pytest.mark.asyncio
async def test_refresh_rules_cache_if_rules_channel(monkeypatch, fake_settings):
    refresh_mock = AsyncMock()
    monkeypatch.setattr(moderation_helper.rules_manager, "RULE_CHANNEL_PATTERN", cast(object, SimpleNamespace(search=lambda name: True)))
    monkeypatch.setattr(moderation_helper.rules_manager, "refresh_guild_rules", refresh_mock)

    guild = FakeGuild(guild_id=20)
    channel = FakeChannel(channel_id=33, guild=guild)
    channel.name = "rules"

    cog = SimpleNamespace(bot=SimpleNamespace(), guild=guild)

    await moderation_helper.refresh_rules_cache_if_rules_channel(
        cog,
        cast(moderation_helper.discord.TextChannel, channel),
    )

    refresh_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_refresh_rules_cache_task_handles_cancel(monkeypatch, fake_settings):
    refresh_cache = AsyncMock(side_effect=asyncio.CancelledError())
    monkeypatch.setattr(moderation_helper.rules_manager, "run_periodic_refresh", refresh_cache)

    cog = SimpleNamespace(bot=SimpleNamespace())

    with pytest.raises(asyncio.CancelledError):
        await moderation_helper.refresh_rules_cache_task(cog)

    refresh_cache.assert_awaited_once()
