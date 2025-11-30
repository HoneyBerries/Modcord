"""
Moderation data structures and processing for Modcord.

This package coordinates the entire moderation pipeline:

- **moderation_datatypes.py**: Core data classes for moderation (ActionType,
  ActionData, ModerationMessage, ModerationUser, ModerationChannelBatch,
  CommandAction subclasses). Handles conversion to/from AI model payloads,
  deduplication of users and messages, and JSON serialization.

- **moderation_parsing.py**: Parses AI model responses into ActionData objects.
  Generates dynamic JSON schemas constrained to valid user IDs and message lists
  to prevent hallucinations. Validates responses against schema before parsing.

- **moderation_helper.py**: High-level batch processing orchestrator. Applies
  server rules and channel guidelines per-guild, executes moderation actions,
  handles permission checks and error recovery.

- **rules_injection_engine.py**: Engine for discovering and injecting server
  rules into the moderation context. Identifies rule channels by naming
  conventions and extracts their content.

- **channel_guidelines_injection_engine.py**: Engine for collecting and
  injecting channel-specific guidelines from channel topics into the
  moderation context.
"""