import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from contextlib import asynccontextmanager

import pytest

from modcord import main
from modcord.ui import console


class FakeBot:
    def __init__(self, *args, **kwargs) -> None:
        self._start = AsyncMock(side_effect=asyncio.CancelledError())
        self._close = AsyncMock()
        self._closed = False
        self.guilds = [SimpleNamespace(id=1)]
        self.user = SimpleNamespace(id=42)
        self.change_presence = AsyncMock()

    async def start(self, token: str) -> None:
        await self._start(token)

    def is_closed(self) -> bool:
        return self._closed

    async def close(self) -> None:
        self._closed = True
        await self._close()

    def add_cog(self, cog) -> None:
        pass


@pytest.mark.asyncio
async def test_async_main_successful_shutdown(monkeypatch):
    monkeypatch.setattr(main, "load_environment", lambda: "token")
    monkeypatch.setattr(main, "build_intents", lambda: "intents")
    monkeypatch.setattr(main, "discord", SimpleNamespace(Bot=FakeBot))
    monkeypatch.setattr(main, "load_cogs", lambda bot: None)
    monkeypatch.setattr(main, "initialize_ai_model", AsyncMock(return_value=None))
    main.model_state.available = True
    
    # Mock console_session as a simple async context manager
    @asynccontextmanager
    async def fake_console_session(control):
        yield control
    
    monkeypatch.setattr(main, "console_session", fake_console_session)
    shutdown_mock = AsyncMock()
    monkeypatch.setattr(main, "shutdown_runtime", shutdown_mock)
    start_bot_mock = AsyncMock(side_effect=asyncio.CancelledError())
    monkeypatch.setattr(main, "start_bot", start_bot_mock)

    result = await main.async_main()

    assert result == 0
    start_bot_mock.assert_awaited_once()
    shutdown_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_main_handles_initialization_failure(monkeypatch):
    monkeypatch.setattr(main, "load_environment", lambda: "token")
    monkeypatch.setattr(main, "build_intents", lambda: "intents")
    monkeypatch.setattr(main, "discord", SimpleNamespace(Bot=FakeBot))
    monkeypatch.setattr(main, "load_cogs", lambda bot: None)
    failure = AsyncMock(side_effect=Exception("init failed"))
    monkeypatch.setattr(main, "initialize_ai_model", failure)
    shutdown_mock = AsyncMock()
    monkeypatch.setattr(main, "shutdown_runtime", shutdown_mock)
    
    # Mock console_session as a simple async context manager
    @asynccontextmanager
    async def fake_console_session(control):
        yield control
    
    monkeypatch.setattr(main, "console_session", fake_console_session)
    monkeypatch.setattr(main, "start_bot", AsyncMock())
    main.model_state.available = False
    main.model_state.init_error = "fatal"

    result = await main.async_main()

    assert result == 1
    shutdown_mock.assert_awaited_once()
