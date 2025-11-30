"""
Moderation data structures and processing for Modcord.

This package coordinates the entire moderation pipeline:

- **moderation_parsing.py**: Parses AI model responses into ActionData objects.
  Generates dynamic JSON schemas constrained to valid user IDs and message lists
  to prevent hallucinations. Validates responses against schema before parsing.

- **moderation_helper.py**: High-level batch processing orchestrator. Applies
  server rules and channel guidelines per-guild, executes moderation actions,
  handles permission checks and error recovery.

- **human_review_manager.py**: Manages flagged content that requires human
  moderator review before action is taken.

- **message_batch_manager.py**: Batches incoming messages by channel for
  efficient AI processing.
"""