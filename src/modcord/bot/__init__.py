"""
Discord bot cogs and event handlers for Modcord.

This package organizes all Discord.py cogs that integrate the moderation system
with Discord's event system:

- **events_listener.py**: Handles bot lifecycle (on_ready), maintains bot presence,
  manages periodic rules cache refresh, and sets up the batch processing pipeline

- **message_listener.py**: Core event handlers for message creation, editing, and
  deletion - converts Discord messages into moderation payloads, downloads images,
  and queues them for batch processing

- **moderation_cmds.py**: Manual moderation slash commands (warn, timeout, kick, ban)
  with permission checks, reason logging, and automatic message deletion windows

- **guild_settings_cmds.py**: Interactive settings panel for per-guild configuration
  of AI enabled state and individual action toggles

- **debug_cmds.py**: Administrative utilities (test, purge, refresh_rules, show_rules)
  for development and debugging
"""