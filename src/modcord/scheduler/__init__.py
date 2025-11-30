"""
Scheduled task execution for time-delayed moderation actions.

This package manages delayed moderation operations:

- **unban_scheduler.py**: Scheduler for automatic unbans after temporary ban
  duration expires. Uses min-heap for efficient O(log n) scheduling, supports
  job cancellation, and coordinates with Discord API for actual unban execution.
  Notifies users via embed when they're unbanned.

- **rules_sync_scheduler.py**: Scheduler for periodic synchronization of server
  rules across all guilds. Runs independently with its own configurable interval.

- **guidelines_sync_scheduler.py**: Scheduler for periodic synchronization of
  channel guidelines across all guilds. Runs independently with its own
  configurable interval.

Key Features:
- Per-guild, per-user job tracking with fast lookup
- Graceful task cancellation and shutdown
- Automatic cleanup of expired jobs
- Parallel sync of rules and guidelines with separate intervals
"""