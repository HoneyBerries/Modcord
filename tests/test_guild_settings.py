import asyncio
import unittest
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

from modcord.configuration.guild_settings import GuildSettingsManager
from modcord.util.moderation_models import ModerationBatch, ModerationMessage


class GuildSettingsBatchingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        patcher = patch(
            "modcord.configuration.guild_settings.app_config",
            MagicMock(ai_settings=MagicMock(batching={"batch_window": 0.01})),
        )
        self.addCleanup(patcher.stop)
        patcher.start()

        self.manager = GuildSettingsManager()
        self.addAsyncCleanup(self.manager.shutdown)

    async def test_add_message_to_batch_schedules_timer(self) -> None:
        channel_id = 123
        message = ModerationMessage(
            message_id="1",
            user_id="u1",
            username="user",
            content="hello",
            timestamp="now",
            guild_id=1,
            channel_id=channel_id,
        )

        callback = AsyncMock()
        self.manager.set_batch_processing_callback(callback)

        await self.manager.add_message_to_batch(channel_id, message)

        self.assertIn(channel_id, self.manager.channel_message_batches)
        self.assertEqual(len(self.manager.channel_message_batches[channel_id]), 1)
        self.assertIn(channel_id, self.manager.channel_batch_timers)

        await asyncio.sleep(0.05)

        callback.assert_awaited_once()
        self.assertEqual(len(callback.await_args_list), 1)
        batch_call = callback.await_args_list[0]
        batch_arg = cast(ModerationBatch, batch_call.args[0])
        self.assertIsInstance(batch_arg, ModerationBatch)
        self.assertEqual(batch_arg.channel_id, channel_id)
        self.assertEqual(len(batch_arg.messages), 1)

    async def test_batch_timer_cancels_on_empty(self) -> None:
        channel_id = 456
        callback = AsyncMock()
        self.manager.set_batch_processing_callback(callback)

        await self.manager.add_message_to_batch(channel_id, ModerationMessage(
            message_id="1",
            user_id="u1",
            username="user",
            content="hello",
            timestamp="now",
            guild_id=1,
            channel_id=channel_id,
        ))

        self.manager.channel_message_batches[channel_id].clear()

        await asyncio.sleep(0.05)

        callback.assert_not_called()
        self.assertNotIn(channel_id, self.manager.channel_batch_timers)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
