import asyncio
import datetime
from types import SimpleNamespace
from typing import Awaitable, Callable, cast
from unittest.mock import AsyncMock

import pytest

from modcord.bot.cogs import events_listener, message_listener
from modcord.util.moderation_datatypes import ModerationMessage


class FakeStatus:
    online = "online"
    idle = "idle"


class FakeActivityType:
    watching = "watching"


class FakeActivity:
    def __init__(self, *, type, name):
        self.type = type
        self.name = name


class FakeMessage:
    def __init__(self, *, guild=None, author=None, content="", channel=None, message_id=0, created_at=None):
        self.guild = guild
        self.author = author
        self.clean_content = content
        self.content = content
        self.channel = channel
        self.id = message_id
        self.created_at = created_at or datetime.datetime.utcnow()


class FakeConnectionError(Exception):
    pass


@pytest.fixture(autouse=True)
def patch_discord(monkeypatch):
    monkeypatch.setattr(events_listener.discord, "Status", FakeStatus, raising=False)
    monkeypatch.setattr(events_listener.discord, "ActivityType", FakeActivityType, raising=False)
    monkeypatch.setattr(events_listener.discord, "Activity", FakeActivity, raising=False)
    monkeypatch.setattr(events_listener.discord, "InteractionResponded", FakeConnectionError, raising=False)
    # Also patch the message_listener module's discord reference so its tests use the same fakes
    monkeypatch.setattr(message_listener.discord, "Status", FakeStatus, raising=False)
    monkeypatch.setattr(message_listener.discord, "ActivityType", FakeActivityType, raising=False)
    monkeypatch.setattr(message_listener.discord, "Activity", FakeActivity, raising=False)
    monkeypatch.setattr(message_listener.discord, "InteractionResponded", FakeConnectionError, raising=False)
    yield


@pytest.fixture
def fake_bot():
    return SimpleNamespace(
        user=SimpleNamespace(id=999, display_name="ModcordBot"),
        change_presence=AsyncMock(),
        guilds=[SimpleNamespace(id=1)],
    )


@pytest.fixture
def patched_dependencies(monkeypatch):
    history_mock = AsyncMock()
    batch_mock = AsyncMock()
    refresh_mock = AsyncMock()
    deps = SimpleNamespace(
        history=history_mock,
        batch=batch_mock,
        refresh=refresh_mock,
        callback=None,
    )

    def set_callback(cb):
        deps.callback = cb

    # Patch both cogs' references to the shared guild_settings_manager so tests using either module
    # receive the same mocked behavior.
    monkeypatch.setattr(events_listener.guild_settings_manager, "set_batch_processing_callback", set_callback)
    monkeypatch.setattr(message_listener.guild_settings_manager, "set_batch_processing_callback", set_callback)

    monkeypatch.setattr(events_listener.guild_settings_manager, "add_message_to_history", history_mock)
    monkeypatch.setattr(message_listener.guild_settings_manager, "add_message_to_history", history_mock)
    monkeypatch.setattr(events_listener.guild_settings_manager, "add_message_to_batch", batch_mock)
    monkeypatch.setattr(message_listener.guild_settings_manager, "add_message_to_batch", batch_mock)

    monkeypatch.setattr(events_listener.guild_settings_manager, "is_ai_enabled", lambda guild_id: True)
    monkeypatch.setattr(message_listener.guild_settings_manager, "is_ai_enabled", lambda guild_id: True)

    monkeypatch.setattr(events_listener.moderation_helper, "refresh_rules_cache_if_rules_channel", refresh_mock)
    monkeypatch.setattr(message_listener.moderation_helper, "refresh_rules_cache_if_rules_channel", refresh_mock)

    monkeypatch.setattr(message_listener.discord_utils, "is_ignored_author", lambda author: False)

    events_listener.model_state.available = True
    events_listener.model_state.init_error = None

    return deps


@pytest.mark.asyncio
async def test_on_ready_sets_presence_and_registers_callbacks(fake_bot, patched_dependencies, monkeypatch):
    create_task_calls: list[asyncio.Task] = []

    def fake_create_task(coro):
        create_task_calls.append(coro)
        class _Task:
            def cancel(self):
                pass
            def done(self):
                return False
        return _Task()

    processor_mock = AsyncMock()
    monkeypatch.setattr(asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(events_listener.moderation_helper, "process_message_batch", processor_mock)

    cog = events_listener.EventsListenerCog(fake_bot)

    await cog.on_ready()

    fake_bot.change_presence.assert_awaited_once()
    assert len(create_task_calls) == 1
    assert callable(patched_dependencies.callback)

    batch = ModerationMessage(
        message_id="m1",
        user_id="u1",
        username="user",
        content="hello",
        timestamp="2024",
        guild_id=1,
        channel_id=1,
    )
    assert patched_dependencies.callback is not None
    callback = cast(Callable[[ModerationMessage], Awaitable[object]], patched_dependencies.callback)
    await callback(batch)
    processor_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_presence_handles_unavailable(fake_bot, patched_dependencies):
    events_listener.model_state.available = False
    events_listener.model_state.init_error = "offline"

    cog = events_listener.EventsListenerCog(fake_bot)

    # method was renamed to a private helper
    await cog._update_presence()

    kwargs = fake_bot.change_presence.await_args.kwargs
    assert kwargs["status"] == FakeStatus.idle
    activity = kwargs["activity"]
    assert isinstance(activity, FakeActivity)
    assert "offline" in activity.name


@pytest.mark.asyncio
async def test_on_message_bails_for_ignored_author(fake_bot, patched_dependencies, monkeypatch):
    monkeypatch.setattr(message_listener.discord_utils, "is_ignored_author", lambda author: True)

    cog = message_listener.MessageListenerCog(fake_bot)

    guild = SimpleNamespace(id=5)
    author = SimpleNamespace(id=6)
    channel = SimpleNamespace(id=10, name="general")
    message = cast(events_listener.discord.Message, FakeMessage(guild=guild, author=author, content="hello", channel=channel, message_id=11))

    await cog.on_message(message)

    patched_dependencies.history.assert_not_called()
    patched_dependencies.batch.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_message_records_and_batches(fake_bot, patched_dependencies):
    cog = message_listener.MessageListenerCog(fake_bot)

    guild = SimpleNamespace(id=7, name="Guild")
    author = SimpleNamespace(id=8)
    channel = SimpleNamespace(id=9, name="general")
    message = cast(events_listener.discord.Message, FakeMessage(guild=guild, author=author, content="  important  ", channel=channel, message_id=12))

    await cog.on_message(message)

    patched_dependencies.history.assert_called_once()
    patched_dependencies.batch.assert_awaited_once()
    patched_dependencies.refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_message_edit_triggers_refresh(fake_bot, patched_dependencies, monkeypatch):
    monkeypatch.setattr(message_listener.discord_utils, "is_ignored_author", lambda author: False)

    cog = message_listener.MessageListenerCog(fake_bot)

    guild = SimpleNamespace(id=3)
    channel = SimpleNamespace(id=13, name="rules", guild=guild)
    before = cast(message_listener.discord.Message, SimpleNamespace(content="old"))
    after = cast(message_listener.discord.Message, SimpleNamespace(content="new", guild=guild, author=SimpleNamespace(id=9), channel=channel))

    await cog.on_message_edit(before, after)

    patched_dependencies.refresh.assert_awaited()


@pytest.mark.asyncio
async def test_application_command_error_responds(fake_bot, patched_dependencies):
    cog = events_listener.EventsListenerCog(fake_bot)

    respond_mock = AsyncMock(side_effect=FakeConnectionError())
    followup_send = AsyncMock()
    ctx = cast(
        events_listener.discord.ApplicationContext,
        SimpleNamespace(
            command=SimpleNamespace(name="cmd"),
            respond=respond_mock,
            followup=SimpleNamespace(send=followup_send),
        ),
    )

    await cog.on_application_command_error(ctx, Exception("boom"))

    respond_mock.assert_awaited_once()
    followup_send.assert_awaited_once()
