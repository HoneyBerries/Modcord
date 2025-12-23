# Moderation Pipeline Architecture

## High-Level View
- Modcord runs as an asynchronous Py-Cord application that layers an AI-driven moderation workflow on top of Discord events. The moderation system is composed of message ingestion, channel batching, AI inference, structured response parsing, and Discord-facing enforcement steps.
- Core services live under `modcord.ai`, `modcord.util`, and `modcord.bot`. They are wired together during startup in `modcord.main` and further orchestrated by bot cogs once the Discord client is connected.
- The AI layer calls an OpenAI-compatible API directly via `ai_moderation_processor` (no local model lifecycle). It builds messages, sends them to the API, and validates JSON-mode responses.
- `ModerationProcessor` translates Discord batches into API-ready payloads, submits prompts, and reconciles AI outputs with real Discord message metadata before any action is taken.

## Bootstrapping & Lifecycle Control
- When the process starts, `main.async_main` loads environment variables, constructs the Py-Cord bot, and initializes persistence. There is no AI warm-up step because the OpenAI API is invoked per request.
- The AI calls are stateless; availability is handled per-request with error handling instead of a shared `model_state` object.
- Once the Discord client signals readiness, the events cog sets the bot presence, starts periodic rule refresh tasks, and registers the moderation batch callback with the guild settings manager.

## Message Intake & Context Gathering
- `MessageListenerCog` consumes `on_message` events, filtering out DMs, bot authors, and empty payloads. Accepted messages are normalized into `ModerationMessage` dataclasses.
- The same listener queues messages for moderation by passing them to the batching manager. Guild-level feature toggles are consulted before queuing so that moderators can disable AI assistance per server.

## Channel Batching Layer
- `MessageBatchManager` orchestrates batched moderation using a **global batching approach**. Messages from each channel are queued independently, but all channels share a single global timer whose length comes from configuration (`moderation_batch_seconds`).
- When the global timer fires, the manager gathers **all pending channel batches** and enriches each with contextual history by pulling fresh messages directly from the Discord API. No local message cache is maintained, ensuring edits and deletions are reflected immediately.
- The manager wraps each channel's messages in a `ModerationChannelBatch` structure and creates a list of all batches. This list is forwarded to the registered callback, which binds back into `moderation_helper.process_message_batches` with access to the cog instance.
- **Key advantage**: All channel batches are processed together in a single vLLM inference call, maximizing GPU utilization and throughput compared to processing each channel individually.

## AI Prompt Composition & Inference
- `ModerationProcessor.get_multi_batch_moderation_actions` transforms **multiple channel batches** into OpenAI API-ready conversations in a single operation. Each batch becomes one conversation in the list:
  - Messages are grouped by user with ordering and message IDs preserved
  - A dynamic JSON schema is built per-channel to constrain AI outputs to valid user IDs and message IDs for that channel
  - Each conversation uses the OpenAI `response_format` JSON schema enforcement (no grammar compilation)
- Before inference, the processor resolves server rules. Per-guild overrides take precedence over default rules declared in the YAML config. Rules text is obtained either from cached guild settings or via the rules manager, which periodically scrapes rule-like channels.
- The processor builds a system prompt inline, injecting rule text into the configured template. Each conversation is formatted with the same system prompt but different message payloads and schemas.
- **Global batch processing**: All conversations are submitted to OpenAI Chat Completions in a single async request. JSON schema is provided via `response_format` so only structured payloads are accepted.

## Response Parsing & Normalization
- Model outputs from each conversation are validated in `moderation_parsing`. Code fences and surrounding text are stripped, payloads are decoded, and JSON schemas are enforced. Channel mismatches, missing fields, or invalid actions result in empty action sets to prevent undefined behavior.
- Parsed actions are normalized into `ActionData` structures. `ModerationProcessor` reconciles AI-provided message IDs against the actual Discord batch so that downstream enforcement is guaranteed to refer to real messages. Missing or mismatched IDs fall back to the most recent known messages for the user to avoid incorrect deletes.
- Actions from all channels are grouped by channel_id and returned as a dictionary. Each channel's action list is then processed independently to apply moderation actions in the correct context.
- Actions marked as `NULL` are filtered out before Discord-facing work begins.

## Enforcement & Discord Integration
- `moderation_helper.apply_batch_action` cross-checks each action against guild policy toggles (warn/delete/timeout/kick/ban). It also ensures the message still exists, the author is a moderatable member, and that the target isn't a privileged user or the guild owner.
- **REVIEW actions** are handled separately through the `HumanReviewManager` to consolidate multiple review requests into a single embed per guild per batch. This prevents notification spam and provides moderators with a clean overview of flagged content.
- Actual enforcement is delegated to `discord_utils.apply_action_decision`, which handles message deletion, DMs, embeds, and Discord API operations. Deleted message IDs are resolved via a lookup map built from the batch; any remaining IDs are retried through direct channel fetches.
- Actions that ban for a finite duration automatically register with `unban_scheduler`, which maintains a heap-based schedule and posts a notification when the unban occurs.
- All enforcement steps are surrounded by Discord-specific error handling so a single failure (e.g., missing permissions on one channel) does not derail the rest of the pipeline.

## Human Moderator Review System
- When the AI model returns a `REVIEW` action, it indicates content that requires human judgment before enforcement. The review system provides a streamlined workflow for moderators to assess flagged content and take appropriate action.
- **Batch consolidation**: Multiple review actions per guild are aggregated by `HumanReviewManager` during batch processing. Instead of sending one embed per flagged user, the system creates a single consolidated embed containing all users requiring review, preventing channel spam.
- **Persistent tracking**: Each review batch is assigned a unique batch ID and stored in the `review_requests` database table with status tracking (`pending`, `resolved`, `dismissed`). This enables audit trails and prevents duplicate reviews.
- **Interactive UI**: Review embeds include interactive buttons via `HumanReviewResolutionView`:
  - **Mark as Resolved**: Updates the embed to show resolved status, disables all buttons, and records the resolving moderator in the database
  - **Quick action buttons**: Five buttons (Warn, Timeout, Kick, Ban, Delete) provide command suggestions to moderators, pre-populating Discord commands with user IDs from the review
- **Context enrichment**: Review embeds automatically include the flagged user's moderation history (past 7 days), message content, jump links, and attached images to give moderators complete context for their decision
- **Role mentions**: Configured moderator roles are mentioned when review embeds are sent to ensure timely human oversight
- **Permission checks**: Only users with manage guild permissions or configured moderator roles can resolve reviews, preventing unauthorized dismissal
- The review system architecture is modular:
  - `review_notifications.py`: Core `HumanReviewManager` class for batch aggregation and embed creation
  - `review_ui.py`: Discord UI components (`HumanReviewResolutionView`) for button interactions
  - `database.py`: `review_requests` table schema with proper indexes and foreign keys
  - `moderation_helper.py`: Integration point where REVIEW actions are intercepted and routed to the manager

## Configuration & Data Flow
- `app_config` is a thread-safe reader around `config/app_config.yml`. It exposes default server rules, the moderation prompt template, and AI settings (including batching windows and history depth).
- `GuildSettingsManager` persists per-guild settings to `data/guild_settings.json`. Settings include whether AI is enabled and whether each automated action type is allowed. Writes happen asynchronously with atomic file replacement to avoid data corruption.
- The rules manager scrapes likely rule channels and persists the aggregated text within guild settings, ensuring that updated rules automatically feed the AI prompt without redeploying the bot.

## Design Principles
- **Fail-safe defaults**: Any missing configuration, parsing error, or unavailable AI model returns neutral actions. This keeps Discord operations safe even if the AI or schema drifts.
- **Separation of concerns**: Each layer (message intake, batching, AI orchestration, parsing, enforcement) owns a narrow responsibility, which simplifies testing and makes unit isolation straightforward.
- **Async-first operations**: All long-running work (batch timers, Discord fetches, model inference) is `async` to align with the Discord gateway loop and avoid blocking the event loop.
- **Deterministic reconciliation**: Message IDs and user ordering are preserved from ingestion through enforcement so moderators can audit which messages triggered an action.
- **Config-driven behavior**: Batching windows, cache tuning, and server rules live in configuration files or guild settings, enabling runtime adjustments without code changes.
- **Graceful degradation**: If the AI model is disabled or fails to initialize, the rest of the bot (manual commands, console, rule management) continues operating, and the presence indicator warns administrators.

## Related Systems
- **Manual moderation commands** reuse the `ActionData` shape via `CommandAction` subclasses, providing a consistent data contract between AI-initiated and moderator-initiated actions.
- **Console UI** (in `modcord.ui.console`) offers interactive control over the running bot, including restart and shutdown flows that tie into the same lifecycle helpers as the Discord client.
- **Logging & telemetry** are centralized through `util.logger`, giving every subsystem its own named logger for easier filtering and debugging.
- **Test harness**: The repository includes extensive pytest coverage across AI parsing, lifecycle, cogs, and utilities. Tests rely on the modular design to inject fakes and exercise edge cases without hitting Discord APIs or real models.

## Operational Considerations
- The AI backend is an OpenAI-compatible HTTP API, so there is no local model to warm up or unload. Availability is handled per-request with retries/error handling.
- Batching still groups conversations for efficiency, but transport latency to the API is the primary variable rather than GPU throughput.
- Shutdown paths cancel batch timers, wait for pending persistence tasks, and drain the unban scheduler to keep exit clean.
- The bot’s presence is a simple availability banner; AI health is inferred from per-request success/failure rather than a global model state.
