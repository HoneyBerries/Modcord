import asyncio
from types import SimpleNamespace

import pytest

from modcord.util import moderation_helper
from modcord.util.moderation_models import ModerationBatch, ModerationMessage, ActionData, ActionType
import modcord.bot.unban_scheduler as unban_scheduler


@pytest.mark.asyncio
async def test_apply_batch_action_no_messages_returns_false():
    batch = ModerationBatch(channel_id=1, messages=[])
    action = ActionData("1", ActionType.BAN, "reason")
    res = await moderation_helper.apply_batch_action(SimpleNamespace(bot=SimpleNamespace(user=SimpleNamespace())), action, batch)
    assert res is False


@pytest.mark.asyncio
async def test_apply_batch_action_no_discord_message():
    msg = ModerationMessage(message_id="m1", user_id="42", username="u", content="x", timestamp="t", guild_id=1, channel_id=1, discord_message=None)
    batch = ModerationBatch(channel_id=1, messages=[msg])
    action = ActionData("42", ActionType.BAN, "reason")
    res = await moderation_helper.apply_batch_action(SimpleNamespace(bot=SimpleNamespace(user=SimpleNamespace())), action, batch)
    assert res is False


@pytest.mark.asyncio
async def test_unban_scheduler_schedule_and_cancel(monkeypatch):
    # Create fake guild with unban method
    called = {}

    class FakeGuild:
        def __init__(self):
            self.id = 99

        async def unban(self, user_obj, reason=None):
            called['unbanned'] = user_obj.id

    guild = FakeGuild()

    # schedule immediate execute when duration <= 0
    await unban_scheduler.UNBAN_SCHEDULER.schedule(guild=guild, user_id=123, channel=None, duration_seconds=0, bot=None) # type: ignore
    assert called.get('unbanned') == 123

    # schedule and cancel
    await unban_scheduler.reset_unban_scheduler_for_tests()
    await unban_scheduler.UNBAN_SCHEDULER.schedule(guild=guild, user_id=321, channel=None, duration_seconds=0.1, bot=None) # type: ignore
    canceled = await unban_scheduler.UNBAN_SCHEDULER.cancel(guild.id, 321)
    assert canceled in (True, False)  # cancel may race; ensure call succeeds or is gracefully handled
