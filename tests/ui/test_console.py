"""Tests for console UI utilities, specifically the close_bot_instance function."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from modcord.ui.console import close_bot_instance


@pytest.mark.asyncio
async def test_close_bot_instance_with_none():
    """Test that close_bot_instance handles None bot gracefully."""
    # Should not raise any exceptions
    await close_bot_instance(None)


@pytest.mark.asyncio
async def test_close_bot_instance_with_closed_bot():
    """Test that close_bot_instance handles already closed bot gracefully."""
    bot = MagicMock()
    bot.is_closed.return_value = True
    
    # Should not raise any exceptions or call any methods
    await close_bot_instance(bot)
    
    # Verify no methods were called on the bot
    bot.change_presence.assert_not_called()
    bot.close.assert_not_called()


@pytest.mark.asyncio
async def test_close_bot_instance_with_active_websocket():
    """Test that close_bot_instance changes presence when websocket is open."""
    bot = MagicMock()
    bot.is_closed.return_value = False
    bot.ws = MagicMock()
    bot.ws.closed = False
    bot.change_presence = AsyncMock()
    bot.close = AsyncMock()
    
    await close_bot_instance(bot, log_close=False)
    
    # Should have called change_presence and close
    bot.change_presence.assert_called_once()
    bot.close.assert_called_once()


@pytest.mark.asyncio
async def test_close_bot_instance_with_closed_websocket():
    """Test that close_bot_instance skips change_presence when websocket is closed."""
    bot = MagicMock()
    bot.is_closed.return_value = False
    bot.ws = MagicMock()
    bot.ws.closed = True  # Websocket is closed
    bot.change_presence = AsyncMock()
    bot.close = AsyncMock()
    
    await close_bot_instance(bot, log_close=False)
    
    # Should NOT have called change_presence, but should have called close
    bot.change_presence.assert_not_called()
    bot.close.assert_called_once()


@pytest.mark.asyncio
async def test_close_bot_instance_with_none_websocket():
    """Test that close_bot_instance skips change_presence when websocket is None."""
    bot = MagicMock()
    bot.is_closed.return_value = False
    bot.ws = None  # No websocket
    bot.change_presence = AsyncMock()
    bot.close = AsyncMock()
    
    await close_bot_instance(bot, log_close=False)
    
    # Should NOT have called change_presence, but should have called close
    bot.change_presence.assert_not_called()
    bot.close.assert_called_once()


@pytest.mark.asyncio
async def test_close_bot_instance_handles_exceptions():
    """Test that close_bot_instance catches exceptions during shutdown."""
    bot = MagicMock()
    bot.is_closed.return_value = False
    bot.ws = MagicMock()
    bot.ws.closed = False
    bot.change_presence = AsyncMock(side_effect=Exception("Connection error"))
    bot.close = AsyncMock()
    
    # Should not raise the exception
    await close_bot_instance(bot, log_close=False)
    
    # close should still be called even though change_presence raised an exception
    bot.close.assert_called_once()
