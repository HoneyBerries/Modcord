"""unban_scheduler.py
=====================

Implements a simple scheduled unban scheduler owned by the `modcord.bot`
package. This module intentionally avoids importing `modcord.util.discord_utils`
to prevent circular imports; notifications on unban are sent using a small,
self-contained embed so the scheduler can live in `modcord.bot`.
"""
import asyncio
import datetime
import heapq
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import discord

from modcord.util.logger import get_logger

logger = get_logger("unban_scheduler")


@dataclass
class ScheduledUnban:
    guild: discord.Guild
    user_id: int
    channel: Optional[discord.abc.Messageable]
    bot: Optional[discord.Client]
    reason: str = "Ban duration expired."


class UnbanScheduler:
    """Central scheduler that coordinates delayed unban tasks."""

    def __init__(self) -> None:
        self.heap: list[tuple[float, int, ScheduledUnban]] = []
        self.pending_keys: Dict[Tuple[int, int], int] = {}
        self.cancelled_ids: set[int] = set()
        self.counter: int = 0
        self.runner_task: asyncio.Task[None] | None = None
        self.condition: asyncio.Condition = asyncio.Condition()

    def ensure_runner(self) -> None:
        loop = asyncio.get_running_loop()
        if self.runner_task is None or self.runner_task.done():
            self.runner_task = loop.create_task(self.run(), name="modcord-unban-scheduler")

    async def schedule(
        self,
        guild: discord.Guild,
        user_id: int,
        channel: Optional[discord.abc.Messageable],
        duration_seconds: float,
        bot: Optional[discord.Client],
        *,
        reason: str = "Ban duration expired."
    ) -> None:
        payload = ScheduledUnban(guild=guild, user_id=user_id, channel=channel, bot=bot, reason=reason)

        if duration_seconds <= 0:
            await self.execute(payload)
            return

        loop = asyncio.get_running_loop()
        run_at = loop.time() + duration_seconds

        async with self.condition:
            self.ensure_runner()
            key = (guild.id, user_id)
            if key in self.pending_keys:
                self.cancelled_ids.add(self.pending_keys[key])

            self.counter += 1
            job_id = self.counter
            heapq.heappush(self.heap, (run_at, job_id, payload))
            self.pending_keys[key] = job_id
            self.condition.notify_all()

    async def cancel(self, guild_id: int, user_id: int) -> bool:
        async with self.condition:
            key = (guild_id, user_id)
            job_id = self.pending_keys.pop(key, None)
            if job_id is None:
                return False

            self.cancelled_ids.add(job_id)
            self.condition.notify_all()
            return True

    async def shutdown(self) -> None:
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
        loop = asyncio.get_running_loop()
        while True:
            async with self.condition:
                while True:
                    if not self.heap:
                        await self.condition.wait()
                        continue

                    run_at, job_id, payload = self.heap[0]

                    if job_id in self.cancelled_ids:
                        heapq.heappop(self.heap)
                        self.cancelled_ids.remove(job_id)
                        self.pending_keys.pop((payload.guild.id, payload.user_id), None)
                        continue

                    delay = run_at - loop.time()
                    if delay > 0:
                        try:
                            await asyncio.wait_for(self.condition.wait(), timeout=delay)
                        except asyncio.TimeoutError:
                            pass
                        continue

                    heapq.heappop(self.heap)
                    self.pending_keys.pop((payload.guild.id, payload.user_id), None)
                    task_payload = payload
                    break

            try:
                await self.execute(task_payload)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(f"Failed to auto-unban user {task_payload.user_id}: {exc}", exc_info=True)

    async def execute(self, payload: ScheduledUnban) -> None:
        guild = payload.guild
        user_id = payload.user_id

        try:
            user_obj = discord.Object(id=user_id)
            await guild.unban(user_obj, reason=payload.reason)
            logger.info(f"Unbanned user {user_id} after ban expired.")

            # Try to notify in the provided channel with a simple embed (keeps this
            # module independent from util.discord_utils).
            if payload.bot and isinstance(payload.channel, (discord.TextChannel, discord.Thread)):
                try:
                    user = await payload.bot.fetch_user(user_id)
                    embed = discord.Embed(
                        title="🔓 User Unbanned",
                        description=f"{user.mention} (`{user.id}`) has been unbanned.\n{payload.reason}",
                        timestamp=datetime.datetime.now(datetime.timezone.utc),
                    )
                    await payload.channel.send(embed=embed)
                except Exception as e:  # noqa: BLE001 - log and continue
                    logger.warning(f"Could not send unban notification for {user_id}: {e}")

        except discord.NotFound:
            logger.warning(f"Could not unban user {user_id}: User not found in ban list.")
        except Exception as e:  # noqa: BLE001 - propagate failure via log only
            logger.error(f"Failed to auto-unban user {user_id}: {e}")


UNBAN_SCHEDULER = UnbanScheduler()


async def schedule_unban(
    guild: discord.Guild,
    user_id: int,
    channel: Optional[discord.abc.Messageable],
    duration_seconds: float,
    bot: Optional[discord.Client],
    *,
    reason: str = "Ban duration expired."
) -> None:
    await UNBAN_SCHEDULER.schedule(
        guild=guild,
        user_id=user_id,
        channel=channel,
        duration_seconds=duration_seconds,
        bot=bot,
        reason=reason,
    )


async def cancel_scheduled_unban(guild_id: int, user_id: int) -> bool:
    return await UNBAN_SCHEDULER.cancel(guild_id, user_id)


async def reset_unban_scheduler_for_tests() -> None:
    global UNBAN_SCHEDULER
    await UNBAN_SCHEDULER.shutdown()
    UNBAN_SCHEDULER = UnbanScheduler()
