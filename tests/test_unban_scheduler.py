"""Tests for unban_scheduler module."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from modcord.scheduler.unban_scheduler import (
    ScheduledUnban,
    UnbanScheduler,
    UNBAN_SCHEDULER,
)


class TestScheduledUnban:
    """Tests for ScheduledUnban dataclass."""

    def test_scheduled_unban_initialization(self):
        """Test ScheduledUnban initialization with required fields."""
        mock_guild = Mock()
        mock_channel = Mock()
        mock_bot = Mock()
        
        unban = ScheduledUnban(
            guild=mock_guild,
            user_id=12345,
            channel=mock_channel,
            bot=mock_bot,
            reason="Test reason"
        )
        
        assert unban.guild is mock_guild
        assert unban.user_id == 12345
        assert unban.channel is mock_channel
        assert unban.bot is mock_bot
        assert unban.reason == "Test reason"

    def test_scheduled_unban_default_reason(self):
        """Test ScheduledUnban uses default reason."""
        mock_guild = Mock()
        
        unban = ScheduledUnban(
            guild=mock_guild,
            user_id=12345,
            channel=None,
            bot=None
        )
        
        assert unban.reason == "Ban duration expired."


class TestUnbanScheduler:
    """Tests for UnbanScheduler class."""

    def test_initialization(self):
        """Test UnbanScheduler initialization."""
        scheduler = UnbanScheduler()
        
        assert scheduler.heap == []
        assert scheduler.pending_keys == {}
        assert scheduler.cancelled_ids == set()
        assert scheduler.counter == 0
        assert scheduler.runner_task is None
        assert scheduler.condition is not None

    @pytest.mark.asyncio
    async def test_ensure_runner_creates_task(self):
        """Test ensure_runner creates background task."""
        scheduler = UnbanScheduler()
        
        # Mock the run method to avoid actually running it
        with patch.object(scheduler, 'run', new_callable=AsyncMock):
            # Ensure we're in an event loop
            scheduler.ensure_runner()
            
            assert scheduler.runner_task is not None
            assert not scheduler.runner_task.done()
            
            # Cleanup
            if scheduler.runner_task:
                scheduler.runner_task.cancel()
                try:
                    await scheduler.runner_task
                except asyncio.CancelledError:
                    pass

    @pytest.mark.asyncio
    async def test_ensure_runner_reuses_active_task(self):
        """Test ensure_runner doesn't create duplicate tasks."""
        scheduler = UnbanScheduler()
        
        with patch.object(scheduler, 'run', new_callable=AsyncMock):
            scheduler.ensure_runner()
            first_task = scheduler.runner_task
            
            scheduler.ensure_runner()
            second_task = scheduler.runner_task
            
            assert first_task is second_task
            
            # Cleanup
            if scheduler.runner_task:
                scheduler.runner_task.cancel()
                try:
                    await scheduler.runner_task
                except asyncio.CancelledError:
                    pass

    @pytest.mark.asyncio
    async def test_schedule_immediate_unban(self):
        """Test schedule with non-positive duration executes immediately."""
        scheduler = UnbanScheduler()
        
        mock_guild = Mock()
        mock_guild.id = 123
        mock_channel = Mock()
        mock_bot = Mock()
        
        with patch.object(scheduler, 'execute', new_callable=AsyncMock) as mock_execute:
            await scheduler.schedule(
                guild=mock_guild,
                user_id=456,
                channel=mock_channel,
                duration_seconds=0,
                bot=mock_bot,
                reason="Immediate"
            )
            
            mock_execute.assert_called_once()
            call_args = mock_execute.call_args[0][0]
            assert isinstance(call_args, ScheduledUnban)
            assert call_args.user_id == 456

    @pytest.mark.asyncio
    async def test_schedule_delayed_unban(self):
        """Test schedule with positive duration adds to heap."""
        scheduler = UnbanScheduler()
        
        mock_guild = Mock()
        mock_guild.id = 123
        
        with patch.object(scheduler, 'run', new_callable=AsyncMock):
            await scheduler.schedule(
                guild=mock_guild,
                user_id=456,
                channel=None,
                duration_seconds=10.0,
                bot=None,
                reason="Delayed"
            )
            
            assert len(scheduler.heap) == 1
            assert scheduler.counter == 1
            assert (123, 456) in scheduler.pending_keys
            
            # Cleanup
            if scheduler.runner_task:
                scheduler.runner_task.cancel()

    @pytest.mark.asyncio
    async def test_schedule_replaces_existing(self):
        """Test scheduling for same user replaces existing job."""
        scheduler = UnbanScheduler()
        
        mock_guild = Mock()
        mock_guild.id = 123
        
        with patch.object(scheduler, 'run', new_callable=AsyncMock):
            # Schedule first job
            await scheduler.schedule(
                guild=mock_guild,
                user_id=456,
                channel=None,
                duration_seconds=10.0,
                bot=None
            )
            
            first_job_id = scheduler.pending_keys[(123, 456)]
            
            # Schedule second job for same user
            await scheduler.schedule(
                guild=mock_guild,
                user_id=456,
                channel=None,
                duration_seconds=20.0,
                bot=None
            )
            
            second_job_id = scheduler.pending_keys[(123, 456)]
            
            assert first_job_id != second_job_id
            assert first_job_id in scheduler.cancelled_ids
            assert len(scheduler.heap) == 2  # Both in heap, but first is cancelled
            
            # Cleanup
            if scheduler.runner_task:
                scheduler.runner_task.cancel()

    @pytest.mark.asyncio
    async def test_cancel_existing_job(self):
        """Test cancel removes a scheduled job."""
        scheduler = UnbanScheduler()
        
        mock_guild = Mock()
        mock_guild.id = 123
        
        with patch.object(scheduler, 'run', new_callable=AsyncMock):
            await scheduler.schedule(
                guild=mock_guild,
                user_id=456,
                channel=None,
                duration_seconds=10.0,
                bot=None
            )
            
            result = await scheduler.cancel(123, 456)
            
            assert result is True
            assert (123, 456) not in scheduler.pending_keys
            # The job_id that was assigned is what gets added to cancelled_ids
            assert len(scheduler.cancelled_ids) == 1
            
            # Cleanup
            if scheduler.runner_task:
                scheduler.runner_task.cancel()

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_job(self):
        """Test cancel returns False for nonexistent job."""
        scheduler = UnbanScheduler()
        
        result = await scheduler.cancel(999, 888)
        
        assert result is False
        assert (999, 888) not in scheduler.pending_keys

    @pytest.mark.asyncio
    async def test_shutdown_cancels_runner(self):
        """Test shutdown cancels the runner task."""
        scheduler = UnbanScheduler()
        
        with patch.object(scheduler, 'run', new_callable=AsyncMock):
            scheduler.ensure_runner()
            assert scheduler.runner_task is not None
            
            await scheduler.shutdown()
            
            assert scheduler.heap == []
            assert scheduler.pending_keys == {}
            assert scheduler.cancelled_ids == set()
            assert scheduler.runner_task is None

    @pytest.mark.asyncio
    async def test_shutdown_handles_no_runner(self):
        """Test shutdown works when no runner exists."""
        scheduler = UnbanScheduler()
        
        # Should not raise error
        await scheduler.shutdown()
        
        assert scheduler.runner_task is None

    @pytest.mark.asyncio
    async def test_execute_unbans_user(self):
        """Test execute performs unban operation."""
        scheduler = UnbanScheduler()
        
        mock_guild = Mock()
        mock_guild.unban = AsyncMock()
        mock_guild.name = "Test Guild"
        
        mock_user = Mock()
        mock_user.id = 456
        mock_user.name = "TestUser"
        
        mock_bot = Mock()
        mock_bot.fetch_user = AsyncMock(return_value=mock_user)
        
        payload = ScheduledUnban(
            guild=mock_guild,
            user_id=456,
            channel=None,
            bot=mock_bot,
            reason="Test unban"
        )
        
        await scheduler.execute(payload)
        
        mock_guild.unban.assert_called_once()
        call_args = mock_guild.unban.call_args
        assert call_args[1]["reason"] == "Test unban"

    @pytest.mark.asyncio
    async def test_execute_sends_notification(self):
        """Test execute sends notification to channel."""
        scheduler = UnbanScheduler()
        
        mock_guild = Mock()
        mock_guild.unban = AsyncMock()
        mock_guild.name = "Test Guild"
        
        mock_user = Mock()
        mock_user.id = 456
        mock_user.name = "TestUser"
        mock_user.mention = "<@456>"
        
        mock_bot = Mock()
        mock_bot.fetch_user = AsyncMock(return_value=mock_user)
        
        # Use TextChannel spec
        from discord import TextChannel
        mock_channel = Mock(spec=TextChannel)
        mock_channel.send = AsyncMock()
        
        payload = ScheduledUnban(
            guild=mock_guild,
            user_id=456,
            channel=mock_channel,
            bot=mock_bot,
            reason="Test"
        )
        
        await scheduler.execute(payload)
        
        # Should send an embed
        mock_channel.send.assert_called_once()
        call_kwargs = mock_channel.send.call_args[1]
        assert 'embed' in call_kwargs

    @pytest.mark.asyncio
    async def test_execute_handles_unban_failure(self):
        """Test execute handles unban errors gracefully."""
        scheduler = UnbanScheduler()
        
        mock_guild = Mock()
        mock_guild.unban = AsyncMock(side_effect=Exception("Unban failed"))
        mock_guild.name = "Test Guild"
        
        payload = ScheduledUnban(
            guild=mock_guild,
            user_id=456,
            channel=None,
            bot=None,
            reason="Test"
        )
        
        # Should not raise exception
        await scheduler.execute(payload)
        
        mock_guild.unban.assert_called_once()


class TestModuleLevelObjects:
    """Test module-level singleton objects."""

    def test_unban_scheduler_singleton(self):
        """Test UNBAN_SCHEDULER is an UnbanScheduler instance."""
        assert isinstance(UNBAN_SCHEDULER, UnbanScheduler)
