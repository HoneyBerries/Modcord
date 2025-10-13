import os
import sys
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest

from modcord import main
from modcord.ui import console


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
    control = console.ConsoleControl()
    class DummyBot:
        def __init__(self) -> None:
            self.close = AsyncMock()

        def is_closed(self) -> bool:
            return False

    dummy_bot = DummyBot()
    control.set_bot(cast(main.discord.Bot, dummy_bot))

    with patch("modcord.ui.console.console_print") as print_mock:
        await console.handle_console_command("shutdown", control)

    assert control.is_shutdown_requested()
    dummy_bot.close.assert_awaited_once()
    print_mock.assert_any_call("Shutdown requested.")


@pytest.mark.asyncio
async def test_handle_console_restart_sets_flag_and_closes_bot():
    control = console.ConsoleControl()
    class DummyBot:
        def __init__(self) -> None:
            self.close = AsyncMock()

        def is_closed(self) -> bool:
            return False

    dummy_bot = DummyBot()
    control.set_bot(cast(main.discord.Bot, dummy_bot))

    with patch("modcord.ui.console.console_print") as print_mock:
        await console.handle_console_command("restart", control)

    assert control.is_restart_requested()
    dummy_bot.close.assert_awaited_once()
    print_mock.assert_any_call("Full restart requested. Bot will shut down and restart...")


@pytest.mark.asyncio
async def test_handle_console_status_reports_state():
    control = console.ConsoleControl()
    fake_bot = cast(main.discord.Bot, SimpleNamespace(guilds=[1, 2, 3]))
    control.set_bot(fake_bot)
    from modcord.ai.ai_moderation_processor import model_state
    model_state.available = True
    model_state.init_error = None

    with patch("modcord.ui.console.console_print") as print_mock:
        await console.handle_console_command("status", control)

    print_mock.assert_called()
    text = " ".join(str(arg) for call in print_mock.call_args_list for arg in call[0])
    assert "Status" in text
    assert "connected guilds: 3" in text


@pytest.mark.asyncio
async def test_handle_console_help_lists_commands():
    control = console.ConsoleControl()

    with patch("modcord.ui.console.console_print") as print_mock:
        await console.handle_console_command("help", control)

    print_mock.assert_called()
    assert any("Available commands" in str(call[0][0]) for call in print_mock.call_args_list)


@pytest.mark.asyncio
async def test_handle_console_unknown_command():
    control = console.ConsoleControl()

    with patch("modcord.ui.console.console_print") as print_mock:
        await console.handle_console_command("unknown", control)

    print_mock.assert_called_once()
    assert "Unknown command" in str(print_mock.call_args[0][0])


def test_main_restarts_with_os_execv_on_exit_code_42():
    """Test that exit code 42 triggers a new process spawn via os.execv."""
    async def mock_async_main():
        return 42

    with patch("modcord.main.asyncio.run", return_value=42):
        with patch("modcord.main.os.execv") as execv_mock:
            with patch("modcord.main.sys.executable", "/usr/bin/python"):
                with patch("modcord.main.sys.argv", ["modcord"]):
                    main.main()

    # Verify os.execv was called to spawn a new process
    execv_mock.assert_called_once_with("/usr/bin/python", ["/usr/bin/python", "modcord"])
