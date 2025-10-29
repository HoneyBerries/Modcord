# Modcord – AI agent guide for this repo

Purpose: Give agents symbol-level entry points to build, test, and extend the bot safely and fast.

## Start here (runtime and lifecycle)
- Entrypoint: `main.main()` and `main.async_main()` — runs the bot and console; exit code 42 triggers restart. Requires `.env: DISCORD_BOT_TOKEN`.
- Bot wiring: `main.load_cogs(bot)` registers cogs; `main.create_bot()` builds `discord.Bot` with `main.build_intents()`.
- AI engine lifecycle: `ai.ai_moderation_processor.initialize_engine()` / `shutdown_engine()`; state in `ai.ai_core.ModelState` via `inference_processor.state`.

## Message → Action pipeline (key symbols)
1) Intake: `bot.message_listener.MessageListenerCog.on_message` → builds `moderation.moderation_datatypes.ModerationMessage` with images (via `util.image_utils`).
2) Batching: `moderation.message_batch_manager.MessageBatchManager`
   - Add/update/remove: `add_message_to_batch`, `update_message_in_batch`, `remove_message_from_batch`
   - Global tick: private `_global_batch_timer_task()` assembles `ModerationChannelBatch` and fetches fresh history via `history.discord_history_fetcher.DiscordHistoryFetcher`.
3) AI orchestration: `ai.ai_moderation_processor.ModerationProcessor.get_multi_batch_moderation_actions(batches, ...)`
   - JSON schema: `moderation.moderation_parsing.build_dynamic_moderation_schema(...)`
   - Guided decoding: `xgrammar.Grammar.from_json_schema(...)`
   - System prompt: `ai.ai_core.InferenceProcessor.get_system_prompt(rules, guidelines)`
   - Batch inference: `InferenceProcessor.generate_multi_chat(conversations, grammar_strings)`
   - Parse: `moderation.moderation_parsing.parse_batch_actions(text, channel_id, schema)` → `ActionData[]`
4) Enforcement: `util.discord_utils.apply_action_decision(action, pivot, bot_user, bot_client, ...)`
   - Notifications: `util.discord_utils.execute_moderation_notification`
   - Deletions: `util.discord_utils.delete_messages_by_ids` / `safe_delete_message`
   - Timed unban: `scheduler.unban_scheduler.schedule_unban`

## Configuration (effective knobs and contracts)
- App config accessor: `configuration.app_configuration.app_config: AppConfig`
  - AI: `AppConfig.ai_settings: AISettings` → `.get("moderation_batch_seconds")`, `.get("history_context_messages")`, `.model_id`, `.enabled`, `.sampling_parameters`
  - Prompt: `AppConfig.system_prompt_template` injects `<|SERVER_RULES_INJECT|>` and `<|CHANNEL_GUIDELINES_INJECT|>`
- Per-guild settings API: `configuration.guild_settings.GuildSettingsManager`
  - Read flags: `is_ai_enabled(guild_id)`, `is_action_allowed(guild_id, ActionType)`
  - Mutations persist asynchronously: `set_ai_enabled`, `set_action_allowed`, `set_server_rules`, `set_channel_guidelines`

## Database (ready out of the box)
- Path: `database.database.DB_PATH` → `data/app.db` (created if missing).
- Init: `database.database.init_database()` creates tables and WAL mode, including `moderation_actions` used by logging/history.
- Usage:
  - Log actions: `database.database.log_moderation_action(guild_id, user_id, action_type, reason, metadata=None)`
  - Query history: `database.database.get_past_actions(guild_id, user_id, lookback_minutes)`

## Conventions that matter here
- Async-first: use `await` everywhere; heavy/blocking work goes through `asyncio.to_thread`.
- Schema-first AI: always produce/expect `ActionData` via `parse_batch_actions` constrained by dynamic JSON schema; no free-form LLM text.
- No local message cache: history is fetched live per batch to respect edits/deletes.
- Fail-safe: if AI is unavailable (`ModelState.available=False`) or parsing fails, treat as neutral actions and keep commands functional.
- Logging: use `util.logger.get_logger(name)`; avoid prints in runtime code.

## Extend safely (where to plug in)
- New moderation outcome: extend `moderation.moderation_datatypes.ActionType` and add handling in `util.discord_utils.apply_action_decision`; update schema builders if fields change.
- New config: add fields in `config/app_config.yml`, access via `AppConfig`/`AISettings` (don’t hardcode globals).
- New commands/cogs: implement under `bot.*`, then register in `main.load_cogs`.

Quick refs: `README.md`, `moderation_logic.md`, `tests/README.md`.
