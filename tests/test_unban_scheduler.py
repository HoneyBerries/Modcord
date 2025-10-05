import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from modcord.bot.unban_scheduler import (
    UnbanScheduler,
    ScheduledUnban,
    reset_unban_scheduler_for_tests,
    schedule_unban,
    cancel_scheduled_unban,
)


class TestUnbanScheduler(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.scheduler = UnbanScheduler()

    async def asyncTearDown(self):
        await self.scheduler.shutdown()

    async def test_schedule_and_execute_unban(self):
        """Test scheduling an unban and ensuring it executes."""
        mock_guild = AsyncMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_user_id = 456
        mock_channel = AsyncMock(spec=discord.TextChannel)
        mock_bot = AsyncMock(spec=discord.Client)
        mock_bot.fetch_user.return_value = AsyncMock(spec=discord.User)

        await self.scheduler.schedule(
            guild=mock_guild,
            user_id=mock_user_id,
            channel=mock_channel,
            duration_seconds=0.1,
            bot=mock_bot,
            reason="Test unban"
        )

        # Wait for the scheduler to run
        await asyncio.sleep(0.2)

        mock_guild.unban.assert_called_once()
        mock_channel.send.assert_called_once()

    async def test_immediate_unban(self):
        """Test that a duration of 0 triggers an immediate unban."""
        mock_guild = AsyncMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_user_id = 456
        mock_channel = AsyncMock(spec=discord.TextChannel)
        mock_bot = AsyncMock(spec=discord.Client)

        await self.scheduler.schedule(
            guild=mock_guild,
            user_id=mock_user_id,
            channel=mock_channel,
            duration_seconds=0,
            bot=mock_bot
        )

        mock_guild.unban.assert_called_once()

    async def test_cancel_unban(self):
        """Test that a scheduled unban can be cancelled."""
        mock_guild = AsyncMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_user_id = 456
        mock_channel = AsyncMock(spec=discord.TextChannel)
        mock_bot = AsyncMock(spec=discord.Client)

        await self.scheduler.schedule(
            guild=mock_guild,
            user_id=mock_user_id,
            channel=mock_channel,
            duration_seconds=5,
            bot=mock_bot
        )

        cancelled = await self.scheduler.cancel(mock_guild.id, mock_user_id)
        self.assertTrue(cancelled)

        # Wait to ensure the unban is not executed
        await asyncio.sleep(0.1)
        mock_guild.unban.assert_not_called()

    async def test_cancel_nonexistent_unban(self):
        """Test that canceling a non-existent unban fails gracefully."""
        cancelled = await self.scheduler.cancel(999, 999)
        self.assertFalse(cancelled)

    @patch('modcord.bot.unban_scheduler.logger')
    async def test_execute_unban_not_found(self, mock_logger):
        """Test that a NotFound error is handled when the user is not banned."""
        mock_guild = AsyncMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.unban.side_effect = discord.NotFound(MagicMock(), "User not banned")
        mock_user_id = 456

        payload = ScheduledUnban(
            guild=mock_guild,
            user_id=mock_user_id,
            channel=None,
            bot=None,
            reason="test"
        )

        await self.scheduler.execute(payload)

        mock_logger.warning.assert_called_with(f"Could not unban user {mock_user_id}: User not found in ban list.")

    async def test_shutdown(self):
        """Test that the scheduler shuts down and cancels tasks."""
        self.scheduler.ensure_runner()
        self.assertIsNotNone(self.scheduler.runner_task)

        await self.scheduler.shutdown()

        self.assertIsNone(self.scheduler.runner_task)
        self.assertTrue(self.scheduler.runner_task is None or self.scheduler.runner_task.done())


class TestUnbanSchedulerHelpers(unittest.IsolatedAsyncioTestCase):

    @patch('modcord.bot.unban_scheduler.UNBAN_SCHEDULER', spec=UnbanScheduler)
    async def test_schedule_unban_helper(self, mock_scheduler):
        """Test the schedule_unban helper function."""
        mock_guild = MagicMock()
        await schedule_unban(
            guild=mock_guild,
            user_id=123,
            channel=None,
            duration_seconds=10,
            bot=None,
            reason="Helper test"
        )
        mock_scheduler.schedule.assert_called_once()

    @patch('modcord.bot.unban_scheduler.UNBAN_SCHEDULER', spec=UnbanScheduler)
    async def test_cancel_unban_helper(self, mock_scheduler):
        """Test the cancel_scheduled_unban helper function."""
        await cancel_scheduled_unban(guild_id=456, user_id=789)
        mock_scheduler.cancel.assert_called_once_with(456, 789)