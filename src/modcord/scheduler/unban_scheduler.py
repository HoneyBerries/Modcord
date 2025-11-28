"""
Implements a simple scheduled unban scheduler owned by the `modcord.bot`
package. This module intentionally avoids importing `modcord.util.discord_utils`
to prevent circular imports; notifications on unban are sent using a small,
self-contained embed so the scheduler can live in `modcord.bot`.
"""
import asyncio
import datetime
import heapq
from dataclasses import dataclass
from typing import Dict, Tuple

import discord

from modcord.datatypes.discord_datatypes import UserID
from modcord.util.logger import get_logger

logger = get_logger("unban_scheduler")


@dataclass
class UnbanData:
    """
    Data structure containing all information needed to execute a scheduled unban.
    
    Attributes:
        guild (discord.Guild): The guild where the ban should be lifted.
        user_id (UserID): Type-safe Discord user ID to unban.
        channel (discord.abc.Messageable | None): Optional channel to send unban notification to.
        bot (discord.Bot | None): Bot instance for fetching user info and sending notifications.
        reason (str): Audit log reason for the unban.
    """
    guild: discord.Guild
    user_id: UserID
    channel: discord.abc.Messageable | None
    bot: discord.Bot | None
    reason: str = "Ban duration expired."


class UnbanScheduler:
    """
    Central scheduler for managing delayed unban operations.
    
    Uses a min-heap to efficiently schedule and execute unbans at precise times.
    Supports cancellation of scheduled unbans and graceful shutdown.
    
    Attributes:
        heap (list): Min-heap of (run_at, job_id, payload) tuples.
        pending_keys (Dict): Maps (guild_id, user_id) to job_id for quick lookup.
        cancelled_ids (set): Set of job IDs that have been cancelled.
        counter (int): Monotonically increasing job ID counter.
        runner_task (asyncio.Task | None): Background task processing the schedule.
        condition (asyncio.Condition): Coordination primitive for task wakeup.
    """

    def __init__(self) -> None:
        self.heap: list[tuple[float, int, UnbanData]] = []
        self.pending_keys: Dict[Tuple[int, str], int] = {}
        self.cancelled_ids: set[int] = set()
        self.counter: int = 0
        self.runner_task: asyncio.Task[None] | None = None
        self.condition: asyncio.Condition = asyncio.Condition()
        self._next_cleanup: int = 0  # Track when to clean up cancelled IDs

    def ensure_runner(self) -> None:
        """
        Create the background runner task if it's not already active.
        
        Checks if the runner task exists and is still running. If not, creates
        a new task to process scheduled unbans.
        """
        loop = asyncio.get_running_loop()
        if self.runner_task is None or self.runner_task.done():
            self.runner_task = loop.create_task(self.run(), name="modcord-unban-scheduler")

    async def schedule(
        self,
        guild: discord.Guild,
        user_id: UserID,
        channel: discord.abc.Messageable | None,
        duration_seconds: float,
        bot: discord.Bot | None,
        *,
        reason: str = "Ban duration expired."
    ) -> None:
        """
        Schedule an unban operation or execute it immediately if duration is non-positive.
        
        If a user already has a pending unban scheduled, the old one is cancelled
        and replaced with the new schedule.
        
        Args:
            guild (discord.Guild): Guild that owns the ban to be lifted.
            user_id (UserID): Type-safe Discord user ID to unban.
            channel (discord.abc.Messageable | None): Optional channel for status notifications.
            duration_seconds (float): Delay before unban; non-positive values trigger immediate unban.
            bot (discord.Bot | None): Bot instance for fetching user info.
            reason (str): Audit log reason for the unban. Defaults to "Ban duration expired.".
        """
        payload = UnbanData(guild=guild, user_id=user_id, channel=channel, bot=bot, reason=reason)

        if duration_seconds <= 0:
            await self.execute(payload)
            return

        loop = asyncio.get_running_loop()
        run_at = loop.time() + duration_seconds

        async with self.condition:
            self.ensure_runner()
            key = (guild.id, str(user_id))
            if key in self.pending_keys:
                self.cancelled_ids.add(self.pending_keys[key])

            self.counter += 1
            job_id = self.counter
            heapq.heappush(self.heap, (run_at, job_id, payload))
            self.pending_keys[key] = job_id
            self.condition.notify_all()

    async def cancel(self, guild_id: int, user_id: UserID) -> bool:
        """
        Cancel a previously scheduled unban if one exists.
        
        Marks the job as cancelled so the runner task will skip it when encountered.
        The job is not immediately removed from the heap for efficiency.
        
        Args:
            guild_id (int): Guild ID that originally scheduled the unban.
            user_id (UserID): Type-safe Discord user ID of the pending unban job.
        
        Returns:
            bool: True if a job was found and cancelled, False if no matching job exists.
        """
        async with self.condition:
            key = (guild_id, str(user_id))
            job_id = self.pending_keys.pop(key, None)
            if job_id is None:
                return False

            self.cancelled_ids.add(job_id)
            self.condition.notify_all()
            return True

    async def shutdown(self) -> None:
        """
        Stop the scheduler, cancel all pending jobs, and clean up resources.
        
        Cancels the runner task, clears all scheduled unbans, and waits for
        the runner task to complete. Safe to call multiple times.
        """
        async with self.condition:
            if self.runner_task:
                self.runner_task.cancel()
            self.heap.clear()
            self.pending_keys.clear()
            self.cancelled_ids.clear()
            self.condition.notify_all()

        if self.runner_task:
            try:
                await self.runner_task
            except asyncio.CancelledError:
                pass
            finally:
                self.runner_task = None

    async def run(self) -> None:
        """
        Main background loop that processes scheduled unbans when their timers elapse.
        
        Continuously monitors the heap for jobs that are ready to execute. When jobs'
        scheduled times arrive, removes them from the heap and executes the unbans.
        Efficiently handles job cancellation by cleaning up cancelled IDs periodically
        and batching job execution.
        
        This method runs until the scheduler is shut down.
        """
        loop = asyncio.get_running_loop()
        while True:
            async with self.condition:
                # Clean up expired cancelled IDs periodically to prevent memory bloat
                self.counter += 1
                if self.counter - self._next_cleanup >= 1000:
                    self.cancelled_ids.clear()
                    self._next_cleanup = self.counter

                # Skip over cancelled jobs at the top of the heap
                while self.heap and self.heap[0][1] in self.cancelled_ids:
                    _, job_id, payload = heapq.heappop(self.heap)
                    self.cancelled_ids.discard(job_id)
                    self.pending_keys.pop((payload.guild.id, str(payload.user_id)), None)

                if not self.heap:
                    await self.condition.wait()
                    continue

                run_at, _, _ = self.heap[0]
                delay = run_at - loop.time()

                if delay > 0:
                    try:
                        await asyncio.wait_for(self.condition.wait(), timeout=delay)
                    except asyncio.TimeoutError:
                        pass
                    continue

                # Pop the ready job
                _, job_id, payload = heapq.heappop(self.heap)
                self.pending_keys.pop((payload.guild.id, str(payload.user_id)), None)
                task_payload = payload

            try:
                await self.execute(task_payload)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Failed to auto-unban user %s: %s", task_payload.user_id, exc)

    async def execute(self, payload: UnbanData) -> None:
        """
        Perform the actual unban operation and send optional notifications.
        
        Unbans the user from the guild using the Discord API and optionally sends
        an embed notification to the specified channel.
        
        Args:
            payload (UnbanData): Structured data describing the unban operation,
                including guild, user, notification preferences, and reason.
        
        Note:
            All errors are caught and logged to prevent scheduler crashes.
        """
        guild = payload.guild
        user_id = payload.user_id

        try:
            user_obj = discord.Object(id=user_id.to_int())
            await guild.unban(user_obj, reason=payload.reason)
            logger.debug("Unbanned user %s after ban expired.", user_id)

            # Try to notify in the provided channel with a simple embed (keeps this
            # module independent from util.discord_utils).
            if payload.bot and isinstance(payload.channel, (discord.TextChannel, discord.Thread)):
                try:
                    user = await payload.bot.fetch_user(user_id.to_int())
                    embed = discord.Embed(
                        title="🔓 User Unbanned",
                        description=f"{user.mention} (`{user.id}`) has been unbanned.\n{payload.reason}",
                        timestamp=datetime.datetime.now(datetime.timezone.utc),
                    )
                    await payload.channel.send(embed=embed)
                except Exception as e:
                    logger.warning(f"Could not send unban notification for {user_id}: {e}")

        except discord.NotFound:
            logger.warning(f"Could not unban user {user_id}: User not found in ban list.")
        except Exception as e:
            logger.error(f"Failed to auto-unban user {user_id}: {e}")


UNBAN_SCHEDULER = UnbanScheduler()