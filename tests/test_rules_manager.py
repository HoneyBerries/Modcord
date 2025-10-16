import asyncio
from types import SimpleNamespace
from typing import List
from unittest.mock import AsyncMock

import pytest

from modcord.bot import rules_manager


class FakeEmbedField:
    def __init__(self, name: str, value: str) -> None:
        self.name = name
        self.value = value


class FakeEmbed:
    def __init__(self, description: str = "", fields: List[FakeEmbedField] | None = None) -> None:
        self.description = description
        self.fields = fields or []


class FakeMessage:
    def __init__(self, content: str = "", embeds: List[FakeEmbed] | None = None) -> None:
        self.content = content
        self.embeds = embeds or []


class FakeTextChannel:
    def __init__(self, name: str, messages: List[FakeMessage]) -> None:
        self.name = name
        self._messages = messages

    async def history(self, oldest_first: bool = True):
        for message in self._messages:
            yield message


class FakeGuild:
    def __init__(self, name: str, channels: List[FakeTextChannel]) -> None:
        self.name = name
        self.text_channels = channels
        self.id = hash(name) & 0xFFFF


class FakeSettings:
    def __init__(self) -> None:
        self.rules = {}
        self.requested_ids: list[int] = []

    def get_guild_settings(self, guild_id: int):
        self.requested_ids.append(guild_id)
        return self.rules.setdefault(guild_id, {})

    def set_server_rules(self, guild_id: int, value: str) -> None:
        self.rules[guild_id] = value

    def list_guild_ids(self):
        return list(self.rules.keys())


@pytest.mark.asyncio
async def test_collect_rules_text_accumulates_messages(monkeypatch):
    messages = [
        FakeMessage("Line one"),
        FakeMessage(embeds=[FakeEmbed(description="Embed description", fields=[FakeEmbedField("Rule", "value")])]),
    ]
    channel = FakeTextChannel("server-rules", messages)
    guild = FakeGuild("Guild", [channel])

    text = await rules_manager.collect_rules_text(guild) # type: ignore

    assert "Line one" in text
    assert "Embed description" in text
    assert "Rule: value" in text


@pytest.mark.asyncio
async def test_collect_rules_text_returns_empty(monkeypatch):
    guild = FakeGuild("Guild", [])

    text = await rules_manager.collect_rules_text(guild) # type: ignore

    assert text == ""


@pytest.mark.asyncio
async def test_refresh_guild_rules_updates_settings(monkeypatch):
    settings = FakeSettings()
    guild = FakeGuild("Guild", [FakeTextChannel("rules", [FakeMessage("content")])])

    monkeypatch.setattr(rules_manager, "collect_rules_text", AsyncMock(return_value="collected"))
    monkeypatch.setattr(rules_manager, "guild_settings_manager", settings)

    result = await rules_manager.refresh_guild_rules(guild)

    assert result == "collected"
    assert settings.rules[guild.id] == "collected"


@pytest.mark.asyncio
async def test_refresh_rules_cache_handles_exceptions(monkeypatch):
    settings = FakeSettings()
    guild_ok = FakeGuild("Good", [])
    guild_fail = FakeGuild("Bad", [])
    bot = SimpleNamespace(guilds=[guild_ok, guild_fail])

    refresh_mock = AsyncMock(side_effect=["ok", Exception("boom")])
    monkeypatch.setattr(rules_manager, "refresh_guild_rules", refresh_mock)
    monkeypatch.setattr(rules_manager, "guild_settings_manager", settings)

    await rules_manager.refresh_rules_cache(bot)

    assert refresh_mock.await_count == 2


@pytest.mark.asyncio
async def test_run_periodic_refresh_cancels(monkeypatch):
    refresh_mock = AsyncMock(side_effect=[None, asyncio.CancelledError()])
    monkeypatch.setattr(rules_manager, "refresh_rules_cache", refresh_mock)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError()))

    bot = SimpleNamespace(guilds=[])

    with pytest.raises(asyncio.CancelledError):
        await rules_manager.run_periodic_refresh(bot, interval_seconds=0.01)

    assert refresh_mock.await_count >= 1