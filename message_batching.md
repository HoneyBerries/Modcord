# Message batching design

This document describes the current message-batching approach used by Modcord. 
The content here is a modern, practical summary suitable for developers and maintainers.

Goals
- Batch messages per-channel to provide context windows for the moderation
  model while avoiding excessive inference requests.
- Ensure deterministic ordering and per-user aggregation for correct action
  assignment.
- Keep batching simple, resilient, and testable.

Architecture overview
- Each guild channel has a transient in-memory batch buffer managed by
  `modcord.configuration.guild_settings.GuildSettingsManager`.
- When a message arrives it is normalized into a `ModerationMessage` and
  appended to the channel's batch.
- A per-channel timer (default: 15s) flushes the batch to a configurable
  callback (defaults to `modcord.util.moderation_helper.process_message_batch`).
- The callback is responsible for composing the model payload and invoking
  `moderation_processor.get_batch_moderation_actions(...)`.

Key behaviors
- Batches preserve message order.
- Batches aggregate messages by user for model-friendly user payloads.
- When the model is unavailable, batches are skipped and optionally
  persisted in-memory for a short window (avoid data loss but keep memory
  bounded).

Failure modes and mitigation
- Model unavailable: short-circuit processing and log a warning. Optionally
  surface the batch to an operator via an admin channel.
- Queue/backpressure: keep batch sizes bounded and drop the oldest messages
  if memory constraints are reached (configurable threshold).

API and extension points
- `GuildSettingsManager.set_batch_processing_callback(callback)` — set the
  async callback invoked when a batch is ready. Signature: callback(batch: ModerationBatch) -> None.
- `ModerationMessage` and `ModerationBatch` are the canonical in-memory
  shapes and provide helpers to format payloads for the AI engine.

Operational tuning
- Batch window (default 15s) and max messages per-batch are configurable
  via `app_config.ai_settings.batching`.
- Use the `/refresh_rules` admin command to force rules re-scan and update
  per-guild server rules used in prompts.

Testing notes
- Unit tests should simulate multiple messages for a single channel and
  assert aggregated payloads and ordering before and after flush.
- Integration tests should verify that model prompts are produced with the
  expected structure (users grouped, timestamps included).

Why this design
- Per-channel batching balances model cost and context needs.
- Grouping by user simplifies the model prompt and makes action attribution
  deterministic.

Open items
- Add optional persistence for unprocessed batches to survive restarts.
- Expose runtime metrics (batch rate, average size) for observability.
