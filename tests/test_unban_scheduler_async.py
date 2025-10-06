from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from modcord.bot.unban_scheduler import ScheduledUnban, UnbanScheduler


class _DummyChannel:
    def __init__(self) -> None:
        self.sent_embeds: list[object] = []

    async def send(self, *, embed: object) -> None:
        self.sent_embeds.append(embed)


@pytest.mark.asyncio
async def test_schedule_immediate_invokes_execute() -> None:
    scheduler = UnbanScheduler()
    guild = MagicMock()
    guild.id = 123

    execute_mock = AsyncMock()
    scheduler.execute = execute_mock  # type: ignore[assignment]

    await scheduler.schedule(guild=guild, user_id=42, channel=None, duration_seconds=0, bot=None)

    execute_mock.assert_awaited_once()
    await scheduler.shutdown()


@pytest.mark.asyncio
async def test_schedule_and_cancel_pending_job() -> None:
    scheduler = UnbanScheduler()
    guild = MagicMock()
    guild.id = 321

    scheduler.execute = AsyncMock()  # type: ignore[assignment]

    await scheduler.schedule(guild=guild, user_id=77, channel=None, duration_seconds=5, bot=None)

    assert (guild.id, 77) in scheduler.pending_keys

    cancelled = await scheduler.cancel(guild.id, 77)
    assert cancelled is True

    await scheduler.shutdown()


@pytest.mark.asyncio
async def test_execute_sends_notification_with_channel_and_bot() -> None:
    scheduler = UnbanScheduler()
    guild = AsyncMock()
    guild.id = 888
    guild.unban = AsyncMock()

    bot = AsyncMock()
    bot.fetch_user.return_value = SimpleNamespace(mention="@user", id=555)

    with patch("modcord.bot.unban_scheduler.discord.Object", side_effect=lambda id: SimpleNamespace(id=id)), \
        patch("modcord.bot.unban_scheduler.discord.Embed", side_effect=lambda **kwargs: kwargs), \
        patch("modcord.bot.unban_scheduler.discord.TextChannel", _DummyChannel), \
        patch("modcord.bot.unban_scheduler.discord.Thread", _DummyChannel):
        channel = _DummyChannel()
        payload = ScheduledUnban(
            guild=guild,
            user_id=555,
            channel=cast(Any, channel),
            bot=bot,
            reason="Timer expired",
        )

        await scheduler.execute(payload)

    guild.unban.assert_awaited_once()
    bot.fetch_user.assert_awaited_once_with(555)
    assert channel.sent_embeds
    await scheduler.shutdown()


@pytest.mark.asyncio
async def test_execute_handles_not_found() -> None:
    scheduler = UnbanScheduler()
    guild = AsyncMock()
    guild.id = 999
    guild.unban = AsyncMock()

    class DummyNotFound(Exception):
        pass

    with patch("modcord.bot.unban_scheduler.discord.Object", side_effect=lambda id: SimpleNamespace(id=id)), \
        patch("modcord.bot.unban_scheduler.discord.NotFound", DummyNotFound):
        guild.unban.side_effect = DummyNotFound("gone")
        payload = ScheduledUnban(guild=guild, user_id=101, channel=None, bot=None)

        await scheduler.execute(payload)

    guild.unban.assert_awaited_once()
    await scheduler.shutdown()
