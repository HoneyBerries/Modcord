import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from modcord import main
from modcord.ui import console


@pytest.fixture(autouse=True)
def restore_env(monkeypatch):
    monkeypatch.delenv("MODCORD_HOME", raising=False)
    yield


def test_resolve_base_dir_uses_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MODCORD_HOME", str(tmp_path))
    resolved = main.resolve_base_dir()
    assert resolved == tmp_path.resolve()


def test_resolve_base_dir_handles_frozen(monkeypatch, tmp_path):
    monkeypatch.delenv("MODCORD_HOME", raising=False)
    monkeypatch.setattr(main.sys, "frozen", True, raising=False)
    monkeypatch.setattr(main.sys, "argv", [str(tmp_path / "bot.exe")], raising=False)
    resolved = main.resolve_base_dir()
    assert resolved == tmp_path.resolve()


def test_load_environment_requires_token(monkeypatch):
    monkeypatch.setattr(main, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.os, "getenv", lambda key: None)
    with pytest.raises(SystemExit) as excinfo:
        main.load_environment()
    assert excinfo.value.code == 1


def test_build_intents_sets_required_flags(monkeypatch):
    class DummyIntents:
        def __init__(self):
            self.message_content = False
            self.guilds = False
            self.messages = False
            self.reactions = False
            self.members = False

        @classmethod
        def default(cls):
            return cls()

    monkeypatch.setattr(main, "discord", SimpleNamespace(Intents=DummyIntents))
    intents = main.build_intents()
    assert intents.message_content is True
    assert intents.guilds is True
    assert intents.messages is True
    assert intents.reactions is True
    assert intents.members is True


def test_load_cogs_invokes_setup(monkeypatch):
    calls: list[str] = []

    def make_setup(name):
        def _setup(bot):
            calls.append(name)
        return _setup

    monkeypatch.setattr("modcord.bot.cogs.debug_cmds.setup", make_setup("debug"))
    monkeypatch.setattr("modcord.bot.cogs.events_listener.setup", make_setup("events"))
    monkeypatch.setattr("modcord.bot.cogs.message_listener.setup", make_setup("message"))
    monkeypatch.setattr("modcord.bot.cogs.guild_settings_cmds.setup", make_setup("guild"))
    monkeypatch.setattr("modcord.bot.cogs.moderation_cmds.setup", make_setup("mod"))

    fake_bot = cast(main.discord.Bot, SimpleNamespace())
    main.load_cogs(fake_bot)

    assert calls == ["debug", "events", "message", "guild", "mod"]


@pytest.mark.asyncio
async def test_initialize_ai_model_handles_unavailable(monkeypatch):
    monkeypatch.setattr(main, "initialize_engine", AsyncMock(return_value=(False, "offline")))
    await main.initialize_ai_model()


@pytest.mark.asyncio
async def test_initialize_ai_model_propagates_exception(monkeypatch):
    monkeypatch.setattr(main, "initialize_engine", AsyncMock(side_effect=RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        await main.initialize_ai_model()


@pytest.mark.asyncio
async def test_start_bot_propagates_cancelled():
    """Test that start_bot handles CancelledError gracefully without propagating."""
    class CancelBot:
        def __init__(self):
            self.started = False

        async def start(self, token):
            raise asyncio.CancelledError()

    bot = cast(main.discord.Bot, CancelBot())
    # CancelledError should be caught and logged, not propagated
    await main.start_bot(bot, "token")  # Should not raise


@pytest.mark.asyncio
async def test_start_bot_propagates_exception():
    class FailBot:
        async def start(self, token):
            raise ValueError("fail")

    bot = cast(main.discord.Bot, FailBot())
    with pytest.raises(ValueError):
        await main.start_bot(bot, "token")


@pytest.mark.asyncio
async def test_shutdown_runtime_closes_bot_and_subsystems(monkeypatch):
    close_mock = AsyncMock()

    class ClosingBot:
        def __init__(self):
            self._closed = False

        def is_closed(self):
            return self._closed

        async def close(self):
            self._closed = True
            await close_mock()

    bot = ClosingBot()
    shutdown_engine = AsyncMock()
    shutdown_settings = AsyncMock()
    monkeypatch.setattr(main, "shutdown_engine", shutdown_engine)
    monkeypatch.setattr(main.guild_settings_manager, "shutdown", shutdown_settings)

    fake_bot = cast(main.discord.Bot, bot)

    await main.shutdown_runtime(fake_bot)

    close_mock.assert_awaited_once()
    shutdown_engine.assert_awaited_once()
    shutdown_settings.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_console_command_shutdown(monkeypatch):
    control = console.ConsoleControl()
    close_mock = AsyncMock()
    bot = cast(main.discord.Bot, SimpleNamespace(is_closed=lambda: False, close=close_mock))
    control.set_bot(bot)

    await console.handle_console_command("shutdown", control)

    assert control.is_shutdown_requested() is True
    close_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_console_command_restart(monkeypatch):
    control = console.ConsoleControl()
    close_mock = AsyncMock()
    bot = cast(main.discord.Bot, SimpleNamespace(is_closed=lambda: False, close=close_mock))
    control.set_bot(bot)

    await console.handle_console_command("restart", control)

    assert control.is_restart_requested() is True
    close_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_console_command_status(monkeypatch):
    control = console.ConsoleControl()
    control.set_bot(cast(main.discord.Bot, SimpleNamespace(guilds=[1, 2, 3])))
    from modcord.ai.ai_moderation_processor import model_state
    model_state.available = False
    model_state.init_error = "offline"

    await console.handle_console_command("status", control)


@pytest.mark.asyncio
async def test_handle_console_command_unknown():
    control = console.ConsoleControl()
    await console.handle_console_command("unknown", control)


def test_main_handles_keyboard_interrupt(monkeypatch):
    def raise_interrupt(coro):
        coro.close()
        raise KeyboardInterrupt()

    monkeypatch.setattr(main.asyncio, "run", raise_interrupt)
    assert main.main() == 0


@pytest.mark.parametrize(
    "exit_code,expected",
    [
        (SystemExit(5), 5),
        (SystemExit(None), 1),
        (SystemExit("7"), 7),
        (SystemExit("bad"), 1),
    ],
)
def test_main_handles_system_exit(monkeypatch, exit_code, expected):
    def raiser(coro):
        coro.close()
        raise exit_code

    monkeypatch.setattr(main.asyncio, "run", raiser)
    assert main.main() == expected


def test_main_handles_generic_exception(monkeypatch):
    def raiser(coro):
        coro.close()
        raise RuntimeError("boom")

    monkeypatch.setattr(main.asyncio, "run", raiser)
    assert main.main() == 1