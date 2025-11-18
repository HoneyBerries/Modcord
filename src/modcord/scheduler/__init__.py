"""
Scheduled task execution for time-delayed moderation actions.

This package manages delayed moderation operations:

- **unban_scheduler.py**: Scheduler for automatic unbans after temporary ban
  duration expires. Uses min-heap for efficient O(log n) scheduling, supports
  job cancellation, and coordinates with Discord API for actual unban execution.
  Notifies users via embed when they're unbanned.

Key Features:
- Per-guild, per-user job tracking with fast lookup
- Graceful task cancellation and shutdown
- Automatic cleanup of expired jobs
"""