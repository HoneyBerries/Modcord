from datetime import timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch
import discord

import pytest

from modcord.util import discord_utils
from modcord.util.moderation_models import ActionData, ActionType, ModerationMessage


class FakeChannel:
    def __init__(self) -> None:
        self.sent_embeds: list = []

    async def send(self, *, embed=None):
        self.sent_embeds.append(embed)


class FakeGuild:
    def __init__(self) -> None:
        self.name = "TestGuild"
        self.ban = AsyncMock()


class FakeAuthor:
    def __init__(self) -> None:
        self.id = 42
        self.display_name = "User"
        self.mention = "@User"
        self.timeout = AsyncMock()


class FakeMessage:
    def __init__(self) -> None:
        self.id = 101
        self.guild = FakeGuild()
        self.author = FakeAuthor()
        self.channel = FakeChannel()


@pytest.fixture(autouse=True)
def patch_discord_types(monkeypatch):
    monkeypatch.setattr(discord_utils.discord, "TextChannel", FakeChannel, raising=False)
    monkeypatch.setattr(discord_utils.discord, "Thread", FakeChannel, raising=False)
    monkeypatch.setattr(discord_utils.discord, "Member", FakeAuthor, raising=False)
    monkeypatch.setattr(discord_utils.datetime, "timedelta", timedelta, raising=False)
    yield


@pytest.mark.asyncio
async def test_apply_action_decision_ban_schedules_unban(monkeypatch):
    pivot_message = FakeMessage()
    pivot = ModerationMessage(
        message_id=str(pivot_message.id),
        user_id=str(pivot_message.author.id),
        username="user",
        content="text",
        timestamp="2024-01-01T00:00:00Z",
        guild_id=1,
        channel_id=10,
        discord_message=cast(discord.Message, pivot_message),
    )
    action = ActionData(
        user_id=str(pivot_message.author.id),
        action=ActionType.BAN,
        reason="Violation",
        message_ids=["m-extra"],
        ban_duration=3600,
    )
    bot_user = cast(discord.ClientUser, SimpleNamespace())
    bot_client = cast(discord.Client, SimpleNamespace())

    safe_delete = AsyncMock(return_value=True)
    delete_messages = AsyncMock(return_value=1)
    send_dm = AsyncMock(return_value=True)
    create_embed = AsyncMock(return_value="EMBED")
    schedule_unban = AsyncMock()

    with patch.object(discord_utils, "safe_delete_message", safe_delete), \
        patch.object(discord_utils, "delete_messages_by_ids", delete_messages), \
        patch.object(discord_utils, "send_dm_to_user", send_dm), \
        patch.object(discord_utils, "create_punishment_embed", create_embed), \
        patch.object(discord_utils, "schedule_unban", schedule_unban):
        result = await discord_utils.apply_action_decision(action, pivot, bot_user, bot_client)

    assert result is True
    safe_delete.assert_awaited_once()
    delete_messages.assert_awaited_once()
    send_dm.assert_awaited()
    schedule_unban.assert_awaited_once()
    args, kwargs = schedule_unban.call_args
    assert kwargs["duration_seconds"] == 3600
    assert pivot_message.channel.sent_embeds == ["EMBED"]


@pytest.mark.asyncio
async def test_apply_action_decision_timeout_calls_timeout(monkeypatch):
    pivot_message = FakeMessage()
    pivot = ModerationMessage(
        message_id=str(pivot_message.id),
        user_id=str(pivot_message.author.id),
        username="user",
        content="text",
        timestamp="2024-01-01T00:00:00Z",
        guild_id=1,
        channel_id=10,
        discord_message=cast(discord.Message, pivot_message),
    )
    action = ActionData(
        user_id=str(pivot_message.author.id),
        action=ActionType.TIMEOUT,
        reason="Timeout",
        message_ids=[],
        timeout_duration=120,
    )
    bot_user = cast(discord.ClientUser, SimpleNamespace())
    bot_client = cast(discord.Client, SimpleNamespace())

    safe_delete = AsyncMock(return_value=True)
    delete_messages = AsyncMock(return_value=0)
    send_dm = AsyncMock(return_value=True)
    create_embed = AsyncMock(return_value="EMBED")

    with patch.object(discord_utils, "safe_delete_message", safe_delete), \
        patch.object(discord_utils, "delete_messages_by_ids", delete_messages), \
        patch.object(discord_utils, "send_dm_to_user", send_dm), \
        patch.object(discord_utils, "create_punishment_embed", create_embed):
        result = await discord_utils.apply_action_decision(action, pivot, bot_user, bot_client)

    assert result is True
    pivot_message.author.timeout.assert_awaited_once()
    send_dm.assert_awaited()
    assert pivot_message.channel.sent_embeds == ["EMBED"]


@pytest.mark.asyncio
async def test_apply_action_decision_warn_posts_embed(monkeypatch):
    pivot_message = FakeMessage()
    pivot = ModerationMessage(
        message_id=str(pivot_message.id),
        user_id=str(pivot_message.author.id),
        username="user",
        content="text",
        timestamp="2024-01-01T00:00:00Z",
        guild_id=1,
        channel_id=10,
        discord_message=cast(discord.Message, pivot_message),
    )
    action = ActionData(
        user_id=str(pivot_message.author.id),
        action=ActionType.WARN,
        reason="Warn",
        message_ids=[],
    )
    bot_user = cast(discord.ClientUser, SimpleNamespace())
    bot_client = cast(discord.Client, SimpleNamespace())

    safe_delete = AsyncMock(return_value=True)
    delete_messages = AsyncMock(return_value=0)
    send_dm = AsyncMock(return_value=True)
    create_embed = AsyncMock(return_value="EMBED")

    with patch.object(discord_utils, "safe_delete_message", safe_delete), \
        patch.object(discord_utils, "delete_messages_by_ids", delete_messages), \
        patch.object(discord_utils, "send_dm_to_user", send_dm), \
        patch.object(discord_utils, "create_punishment_embed", create_embed):
        result = await discord_utils.apply_action_decision(action, pivot, bot_user, bot_client)

    assert result is True
    send_dm.assert_awaited()
    assert pivot_message.channel.sent_embeds == ["EMBED"]


@pytest.mark.asyncio
async def test_apply_action_decision_delete_returns_immediately(monkeypatch):
    pivot_message = FakeMessage()
    pivot = ModerationMessage(
        message_id=str(pivot_message.id),
        user_id=str(pivot_message.author.id),
        username="user",
        content="text",
        timestamp="2024-01-01T00:00:00Z",
        guild_id=1,
        channel_id=10,
        discord_message=cast(discord.Message, pivot_message),
    )
    action = ActionData(
        user_id=str(pivot_message.author.id),
        action=ActionType.DELETE,
        reason="Delete",
        message_ids=[],
    )
    bot_user = cast(discord.ClientUser, SimpleNamespace())
    bot_client = cast(discord.Client, SimpleNamespace())

    safe_delete = AsyncMock(return_value=True)
    delete_messages = AsyncMock(return_value=0)

    with patch.object(discord_utils, "safe_delete_message", safe_delete), \
        patch.object(discord_utils, "delete_messages_by_ids", delete_messages):
        result = await discord_utils.apply_action_decision(action, pivot, bot_user, bot_client)

    assert result is True
    safe_delete.assert_awaited_once()
    delete_messages.assert_not_called()
    assert pivot_message.channel.sent_embeds == []
