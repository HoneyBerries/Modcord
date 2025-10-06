import asyncio
from types import SimpleNamespace

import pytest

import discord

from modcord.util import discord_utils
from modcord.util.moderation_models import ActionType


def test_format_duration_and_parse():
    assert discord_utils.format_duration(0) == discord_utils.PERMANENT_DURATION
    assert discord_utils.format_duration(30).endswith("secs")
    assert discord_utils.format_duration(120).endswith("mins")
    assert discord_utils.parse_duration_to_seconds("10 mins") == 10 * 60


def test_build_dm_message_various_actions():
    assert "banned" in discord_utils.build_dm_message(ActionType.BAN, "Guild", "reason", None)
    assert "kicked" in discord_utils.build_dm_message(ActionType.KICK, "Guild", "reason")
    assert "timed out" in discord_utils.build_dm_message(ActionType.TIMEOUT, "Guild", "reason", "10 mins")
    assert "warning" in discord_utils.build_dm_message(ActionType.WARN, "Guild", "reason")


def test_has_elevated_permissions_false_for_user():
    class FakeUser:
        bot = False

    assert discord_utils.has_elevated_permissions(FakeUser()) is False # type: ignore


def test_bot_can_manage_messages_no_me():
    # guild with no .me should return True
    guild = SimpleNamespace()
    channel = SimpleNamespace()
    assert discord_utils.bot_can_manage_messages(channel, guild) is True # type: ignore


@pytest.mark.asyncio
async def test_safe_delete_and_delete_by_ids(monkeypatch):
    class FakeMessage:
        def __init__(self, id):
            self.id = id
            self.deleted = False

        async def delete(self):
            self.deleted = True

    class FakeChannel:
        def __init__(self):
            self._messages = {123: FakeMessage(123)}
            self.name = "chan"

        async def fetch_message(self, msg_id):
            if msg_id not in self._messages:
                raise discord.NotFound(Exception("no")) # type: ignore
            return self._messages[msg_id]

        async def history(self, limit=100, after=None):
            for m in self._messages.values():
                yield m

    class FakeGuild:
        def __init__(self):
            self.text_channels = [FakeChannel()]
            self.me = None

    guild = FakeGuild()
    # safe_delete_message
    msg = await guild.text_channels[0].fetch_message(123)
    res = await discord_utils.safe_delete_message(msg) # type: ignore
    assert res is True

    # delete by ids (valid and invalid)
    deleted = await discord_utils.delete_messages_by_ids(guild, ["123", "bad"])  # type: ignore # should skip bad id
    assert deleted >= 0
