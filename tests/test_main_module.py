import os
import sys
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest

from modcord import main


@pytest.fixture(autouse=True)
def _restore_env(monkeypatch):
    original_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original_env)


def test_resolve_base_dir_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("MODCORD_HOME", str(tmp_path))

    resolved = main.resolve_base_dir()

    assert resolved == tmp_path.resolve()


def test_resolve_base_dir_compiled(tmp_path, monkeypatch):
    monkeypatch.delenv("MODCORD_HOME", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "modcord.exe")])

    resolved = main.resolve_base_dir()

    assert resolved == (tmp_path / "modcord.exe").resolve().parent

    monkeypatch.delattr(sys, "frozen", raising=False)


def test_resolve_base_dir_source(monkeypatch):
    monkeypatch.delenv("MODCORD_HOME", raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "compiled", False, raising=False)

    resolved = main.resolve_base_dir()

    assert resolved == main.Path(main.__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_handle_console_shutdown_requests_and_closes():
    control = main.ConsoleControl()
    class DummyBot:
        def __init__(self) -> None:
            self.close = AsyncMock()

        def is_closed(self) -> bool:
            return False

    dummy_bot = DummyBot()
    control.set_bot(cast(main.discord.Bot, dummy_bot))

    with patch.object(main.console, "print") as print_mock:
        await main.handle_console_command("shutdown", control)

    assert control.is_shutdown_requested()
    dummy_bot.close.assert_awaited_once()
    print_mock.assert_any_call("Shutdown requested.")


@pytest.mark.asyncio
async def test_handle_console_restart_invokes_restart():
    control = main.ConsoleControl()
    restart_mock = AsyncMock()

    with patch("modcord.main.restart_ai_engine", restart_mock):
        await main.handle_console_command("restart", control)

    restart_mock.assert_awaited_once_with(control)


@pytest.mark.asyncio
async def test_handle_console_status_reports_state():
    control = main.ConsoleControl()
    fake_bot = cast(main.discord.Bot, SimpleNamespace(guilds=[1, 2, 3]))
    control.set_bot(fake_bot)
    main.model_state.available = True
    main.model_state.init_error = None

    with patch.object(main.console, "print") as print_mock:
        await main.handle_console_command("status", control)

    print_mock.assert_called()
    text = " ".join(str(arg) for call in print_mock.call_args_list for arg in call[0])
    assert "Status" in text
    assert "connected guilds: 3" in text


@pytest.mark.asyncio
async def test_handle_console_help_lists_commands():
    control = main.ConsoleControl()

    with patch.object(main.console, "print") as print_mock:
        await main.handle_console_command("help", control)

    print_mock.assert_called_once()
    assert "Commands" in str(print_mock.call_args[0][0])


@pytest.mark.asyncio
async def test_handle_console_unknown_command():
    control = main.ConsoleControl()

    with patch.object(main.console, "print") as print_mock:
        await main.handle_console_command("unknown", control)

    print_mock.assert_called_once()
    assert "Unknown command" in str(print_mock.call_args[0][0])
