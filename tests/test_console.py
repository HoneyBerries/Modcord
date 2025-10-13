"""Tests for console.py module."""
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from modcord.ui import console
from modcord.ai.ai_moderation_processor import model_state


@pytest.mark.asyncio
async def test_console_print_without_style():
    """Test console_print without style."""
    with patch("modcord.ui.console.print_formatted_text") as mock_print:
        console.console_print("Test message")
        mock_print.assert_called_once_with("Test message")


@pytest.mark.asyncio
async def test_console_print_with_style():
    """Test console_print with style."""
    with patch("modcord.ui.console.print_formatted_text") as mock_print:
        console.console_print("Test message", "ansigreen")
        # Should be called with FormattedText
        assert mock_print.call_count == 1


def test_console_control_stop():
    """Test ConsoleControl.stop() method."""
    control = console.ConsoleControl()
    assert not control.is_shutdown_requested()
    control.stop()
    assert control.is_shutdown_requested()


@pytest.mark.asyncio
async def test_close_bot_instance_when_none():
    """Test close_bot_instance with None bot."""
    # Should not raise
    await console.close_bot_instance(None)
    await console.close_bot_instance(None, log_close=True)


@pytest.mark.asyncio
async def test_close_bot_instance_when_already_closed():
    """Test close_bot_instance with already closed bot."""
    class ClosedBot:
        def is_closed(self):
            return True
    
    bot = ClosedBot()
    # Should not raise and not try to close
    await console.close_bot_instance(bot)


@pytest.mark.asyncio
async def test_close_bot_instance_with_exception():
    """Test close_bot_instance handles exceptions during close."""
    class FailBot:
        def is_closed(self):
            return False
        
        async def close(self):
            raise RuntimeError("Close failed")
    
    bot = FailBot()
    # Should not raise, exception is caught
    await console.close_bot_instance(bot, log_close=True)


@pytest.mark.asyncio
async def test_handle_console_command_empty():
    """Test handle_console_command with empty command."""
    control = console.ConsoleControl()
    # Should not raise
    await console.handle_console_command("", control)
    await console.handle_console_command("   ", control)


@pytest.mark.asyncio
async def test_handle_console_command_quit():
    """Test handle_console_command with quit command."""
    control = console.ConsoleControl()
    fake_bot = SimpleNamespace(is_closed=lambda: False, close=AsyncMock())
    control.set_bot(fake_bot)
    
    with patch("modcord.ui.console.console_print"):
        await console.handle_console_command("quit", control)
    
    assert control.is_shutdown_requested()
    assert not control.is_restart_requested()
    fake_bot.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_console_command_exit():
    """Test handle_console_command with exit command."""
    control = console.ConsoleControl()
    fake_bot = SimpleNamespace(is_closed=lambda: False, close=AsyncMock())
    control.set_bot(fake_bot)
    
    with patch("modcord.ui.console.console_print"):
        await console.handle_console_command("exit", control)
    
    assert control.is_shutdown_requested()
    fake_bot.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_console_with_eof():
    """Test run_console handles EOFError."""
    control = console.ConsoleControl()
    
    async def fake_prompt():
        # First call raises EOFError to simulate Ctrl+D
        raise EOFError()
    
    fake_session = SimpleNamespace(prompt_async=fake_prompt)
    
    with patch("modcord.ui.console.PromptSession", return_value=fake_session):
        with patch("modcord.ui.console.console_print"):
            with patch("modcord.ui.console.patch_stdout"):
                await console.run_console(control)
    
    assert control.is_shutdown_requested()


@pytest.mark.asyncio
async def test_run_console_with_keyboard_interrupt():
    """Test run_console handles KeyboardInterrupt."""
    control = console.ConsoleControl()
    
    async def fake_prompt():
        # First call raises KeyboardInterrupt to simulate Ctrl+C
        raise KeyboardInterrupt()
    
    fake_session = SimpleNamespace(prompt_async=fake_prompt)
    
    with patch("modcord.ui.console.PromptSession", return_value=fake_session):
        with patch("modcord.ui.console.console_print"):
            with patch("modcord.ui.console.patch_stdout"):
                await console.run_console(control)
    
    assert control.is_shutdown_requested()


@pytest.mark.asyncio
async def test_run_console_with_generic_exception():
    """Test run_console handles generic exceptions."""
    control = console.ConsoleControl()
    
    call_count = [0]
    
    async def fake_prompt():
        call_count[0] += 1
        if call_count[0] == 1:
            # First call raises a generic exception
            raise ValueError("Test error")
        else:
            # Second call triggers shutdown
            control.request_shutdown()
            return ""
    
    fake_session = SimpleNamespace(prompt_async=fake_prompt)
    
    with patch("modcord.ui.console.PromptSession", return_value=fake_session):
        with patch("modcord.ui.console.console_print"):
            with patch("modcord.ui.console.patch_stdout"):
                await console.run_console(control)
    
    # Should have continued after exception
    assert call_count[0] >= 2


@pytest.mark.asyncio
async def test_console_session_context_manager():
    """Test console_session context manager."""
    control = console.ConsoleControl()
    
    # Mock run_console to avoid actually running it
    with patch("modcord.ui.console.run_console", new_callable=AsyncMock) as mock_run:
        async with console.console_session(control) as ctrl:
            assert ctrl is control
            # Task should be created
        
        # After exiting, stop should be called
        assert control.is_shutdown_requested()
