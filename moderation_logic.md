# Moderation Pipeline Architecture

## High-Level View
- Modcord runs as an asynchronous Py-Cord application that layers an AI-driven moderation workflow on top of Discord events. The moderation system is composed of message ingestion, channel batching, AI inference, structured response parsing, and Discord-facing enforcement steps.
- Core services live under `modcord.ai`, `modcord.util`, and `modcord.bot`. They are wired together during startup in `modcord.main` and further orchestrated by bot cogs once the Discord client is connected.
- The AI model is hosted through vLLM and wrapped by `InferenceProcessor`, which exposes lifecycle hooks, prompt assembly helpers, and JSON-guided decoding to guarantee machine-readable responses.
- `ModerationProcessor` is a higher-level coordinator that translates Discord batches into model-ready payloads, submits prompts, and reconciles AI outputs with real Discord message metadata before any action is taken.

## Bootstrapping & Lifecycle Control
- When the process starts, `main.async_main` loads environment variables, constructs the Py-Cord bot, and initializes the AI layer. The initialization path reloads configuration, warms the model, and logs availability in a shared `model_state` object.
- The AI lifecycle module offers restart and shutdown hooks, ensuring the inference engine can be reloaded without restarting the whole bot and that resources are cleaned up on exit.
- Once the Discord client signals readiness, the events cog sets the bot presence based on AI health, starts periodic rule refresh tasks, and registers the moderation batch callback with the guild settings manager.

## Message Intake & Context Gathering
- `MessageListenerCog` consumes `on_message` events, filtering out DMs, bot authors, and empty payloads. Accepted messages are normalized into `ModerationMessage` dataclasses.
- Every accepted message is added to a per-channel history cache through `guild_settings_manager.add_message_to_history`, allowing the system to reconstruct context even if the bot was offline when older messages were posted.
- The same listener queues messages for moderation by passing them to the manager’s batching layer. Guild-level feature toggles are consulted before queuing so that moderators can disable AI assistance per server.

## Channel Batching Layer
- `GuildSettingsManager` orchestrates batched moderation. Each channel has an in-memory queue and an associated timer whose length comes from configuration (`moderation_batch_seconds`).
- When the timer fires, the manager gathers the queued messages and enriches them with contextual history via `message_history_cache.fetch_history_for_context`, which blends cached content with on-demand Discord API fetches if necessary.
- The manager wraps everything in a `ModerationChannelBatch` structure and forwards it to the registered callback. The callback, set during startup, binds back into `moderation_helper.process_message_batch` with access to the cog instance.

## AI Prompt Composition & Inference
- `ModerationProcessor.get_batch_moderation_actions` transforms a batch into a JSON payload that groups messages by user, tracks ordering, and records the precise message IDs produced in Discord.
- Before inference, the processor resolves server rules. Per-guild overrides take precedence over default rules declared in the YAML config. Rules text is obtained either from cached guild settings or via the rules manager, which periodically scrapes rule-like channels.
- The processor requests a system prompt from `InferenceProcessor`, which injects rule text into the configured template. Messages are then serialized using the model tokenizer’s chat template to align with vLLM expectations.
- Guided decoding is enabled through xgrammar. A JSON schema (shared with the parser) is compiled once and applied to every generation, ensuring that probabilities collapse onto valid moderation payloads even if the model attempts free-form responses.

## Response Parsing & Normalization
- Model output is validated in `moderation_parsing`. Code fences and surrounding text are stripped, the payload is decoded, and the JSON schema is enforced. Channel mismatches, missing fields, or invalid actions result in an empty action set to prevent undefined behavior.
- Parsed actions are normalized into `ActionData` structures. `ModerationProcessor` reconciles AI-provided message IDs against the actual Discord batch so that downstream enforcement is guaranteed to refer to real messages. Missing or mismatched IDs fall back to the most recent known messages for the user to avoid incorrect deletes.
- A final list of `ActionData` objects is returned to the helper layer. Actions marked as `NULL` are filtered out before Discord-facing work begins.

## Enforcement & Discord Integration
- `moderation_helper.apply_batch_action` cross-checks each action against guild policy toggles (warn/delete/timeout/kick/ban). It also ensures the message still exists, the author is a moderatable member, and that the target isn’t a privileged user or the guild owner.
- Actual enforcement is delegated to `discord_utils.apply_action_decision`, which handles message deletion, DMs, embeds, and Discord API operations. Deleted message IDs are resolved via a lookup map built from the batch; any remaining IDs are retried through direct channel fetches.
- Actions that ban for a finite duration automatically register with `unban_scheduler`, which maintains a heap-based schedule and posts a notification when the unban occurs.
- All enforcement steps are surrounded by Discord-specific error handling so a single failure (e.g., missing permissions on one channel) does not derail the rest of the pipeline.

## Configuration & Data Flow
- `app_config` is a thread-safe reader around `config/app_config.yml`. It exposes default server rules, the moderation prompt template, AI settings, and batching/ cache tuning parameters.
- `GuildSettingsManager` persists per-guild settings to `data/guild_settings.json`. Settings include whether AI is enabled and whether each automated action type is allowed. Writes happen asynchronously with atomic file replacement to avoid data corruption.
- Channel history is stored in `MessageHistoryCache`, which supports TTL-based eviction and API fallback. The cache is reconfigured during startup if the YAML provides overrides for size, TTL, or fetch limits.
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
- The AI backend depends on vLLM, torch, and xgrammar. Initialization checks availability and adjusts sampling dtypes when CUDA is absent. Memory usage is shaped by `vram_percentage` from the config.
- Warm-up runs ensure that the first real moderation batch does not inherit the cold-start latency of vLLM.
- Shutdown paths cancel batch timers, wait for pending persistence tasks, unload the AI model, and drain the unban scheduler to keep exit clean.
- The bot’s presence is a live signal of AI health, allowing moderators to know when automated enforcement is unavailable and manual monitoring is required.
