# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the bot (with DEBUG logging)
./gradlew run

# Run with --test flag (auto-shuts down after 5 seconds for testing)
./gradlew runTest

# Build a fat/shadow JAR (creates build/libs/modcord-all.jar)
./gradlew assemble

# Run all unit tests
./gradlew test

# Run integration tests only (hits a Testcontainers-backed Postgres; some also require a live Discord bot + test guild or a real LLM API key)
./gradlew integrationTest

# Format code with Spotless
./gradlew spotlessApply
```

Set log level via JVM flag: `-DLOG_LEVEL=INFO|DEBUG|WARN|ERROR` (defaults to DEBUG in Gradle tasks, INFO in production).

## Environment Setup

Copy `.env.example` to `.env` and fill in:

```
DISCORD_BOT_TOKEN=<your Discord bot token>
OPENAI_API_KEY=<your OpenAI/LLM provider API key>
POSTGRES_DB_PASSWORD=<database password>
```

Runtime config lives in `config/app_config.yml`:
- **Database:** PostgreSQL connection (host, port, database, username; password from env var)
- **Cache:** Refresh intervals for guild rules and channel guidelines (default: 60s)
- **Moderation:** Queue duration (default: 30s), history context window (default: 50 messages, max age 24h)
- **AI Inference:** Base URL (OpenAI-compatible endpoint), model name, request timeout (default: 3600s)
- **Generic rules/guidelines:** Fallback text for servers with no custom configuration

The system prompt is in `config/system_prompt.md` — customize to fit your community's values.

## Architecture

Modcord is an AI-powered Discord moderation bot. Java 25, Gradle, JDA, PostgreSQL (via HikariCP), Liquibase for schema migrations, OpenAI-compatible inference client (with Resilience4j retry/circuit breaker).

### Startup flow (`Main.java`)

1. `Database.initialize(AppConfig)` — opens HikariCP pool, runs Liquibase migrations
2. `JDAManager.getInstance()` — connects to Discord, registers all slash commands and event listeners
3. Scheduled tasks start: `UnbanWatcherTask`, `GuildRulesTask`, `ChannelGuidelinesTask` (thread pool: 8 threads)
4. `GlobalOrchestrationService` is implicitly initialized on first message — maintains per-guild queues and scheduling logic

**Shutdown flow:** gracefully stops tasks, drops pending moderation queues, shuts down the bot, closes database. Safe even if startup failed partway through.

### Message processing pipeline

The core flow is message → batch → AI → action. Resilience is built in at the inference layer:

1. **`MessageListener`** receives Discord message events, calls `GlobalOrchestrationService.addMessage()`
2. **`GlobalOrchestrationService`** (singleton) maintains per-guild queues and schedules a delayed processing run (default: 30s via config `queue_duration`). Coalesces rapid arrivals into a single batch. Prevents concurrent processing via an in-flight set; if new messages arrive during processing, reschedules a new run after the current one completes.
3. **`GuildMessageProcessingService`** (one per guild, lazily created) manages the message queue with arrival timestamps. When `runPipeline()` is called:
   - Gets queued messages (current window)
   - Fetches historical context from Discord via `HistoryFetcher` (configurable window: `num_history_context_messages`, `history_context_max_age`)
   - Builds `GuildModerationBatch` with `ModerationUser` objects (user details, roles, per-channel message lists)
   - Generates a dynamic JSON schema via `DynamicSchemaGenerator` (constrains AI output to actual users/channels in the batch)
   - Builds the dynamic system prompt via `DynamicSystemPrompt` (injects guild-specific rules and channel guidelines from DB)
   - Calls `InferenceEngine.generateResponse()` (async, wrapped in Resilience4j retry + circuit breaker)
   - Parses the JSON response via `ActionDataJSONParser` into `ActionData` objects
   - Logs to DB (`AILogRepository`, `GuildModerationActionsRepository`)
   - Executes actions in parallel via `ActionHandler`
4. **`ActionHandler`** (singleton) executes each `ActionData`: sends user DM → deletes flagged messages → applies moderation action (timeout/kick/ban/unban) → posts to audit log channel

**Inference resilience (Resilience4j):** InferenceEngine decorates all OpenAI calls with circuit breaker → retry pattern. Retries are transparent to the circuit breaker (all retry attempts count as one failure). Circuit opens after threshold failures; calls rejected immediately until half-open → probe succeeds. Retry and circuit breaker state are logged and exposed via `/status` command.

### Key singletons

All major services are singletons accessed via `getInstance()`: `Database`, `AppConfig`, `JDAManager`, `GlobalOrchestrationService`, `InferenceEngine`, `PreferencesManager`, `DynamicSchemaGenerator`, `DynamicSystemPrompt`, `ActionHandler`.

### Data model

- **`datatypes/discord/`** — typed ID wrappers (`GuildID`, `UserID`, `ChannelID`, `MessageID`, `RoleID`) that wrap `long` to prevent accidental ID mix-ups
- **`datatypes/action/`** — `ActionData` (immutable record: target user, action type, reason, durations, message deletions), `ActionType` enum (BAN, UNBAN, KICK, WARN, DELETE, TIMEOUT, NULL)
- **`datatypes/content/`** — `GuildModerationBatch`, `ModerationUser`, `ModerationUserChannel`, `ModerationMessage` used to assemble the AI input
- **`datatypes/preferences/`** — `GuildPreferences` immutable record with wither methods and a `Builder`

### Database layer

`Database` is a thin singleton wrapping HikariCP. All repositories use its `query()`, `transaction()`, and `executeUpdate()` helpers. Schema is managed by Liquibase changesets under `src/main/resources/db/changelog/`.

### Guild preferences

`GuildPreferences` is stored per guild and controls: AI enabled/disabled, per-action enables (warn, delete, timeout, kick, ban), rules channel, audit log channel. `PreferencesManager` provides `getOrDefaultPreferences()` which falls back to all-enabled defaults. Slash commands in `PreferencesCommands` expose these settings to Discord admins.

### Tests

**Unit tests** run with `./gradlew test` (no external dependencies, no network access):
- `AppConfigTest` — validates `config/app_config.yml` parsing

**Integration tests** (tagged `@Tag("integration")`) touch a real database and/or the real LLM/Discord APIs. Run with `./gradlew integrationTest`.
- Database-repository tests (`net.honeyberries.database.*`) extend `PostgresTestSupport`, which starts a throwaway Postgres Testcontainer (Liquibase migrations applied automatically) instead of touching the shared Azure-hosted database — no external DB access or secrets required.
- `InferenceEngineTest$AIInferenceTests` and `TestImageIDTagging` make real calls to the configured LLM endpoint and need `OPENAI_API_KEY`.
- `TestActionHandler` and `TestRollbackHandler` additionally require a live Discord bot + test guild; they use JUnit `Assumptions` to skip gracefully if the bot isn't connected (configurable via hardcoded guild IDs in test class).

Failures in integration tests don't block CI if bot is unavailable (graceful skip).

## Java 25+ Features

The codebase uses Java 25-specific APIs:
- **Virtual threads** (`Thread.startVirtualThread()`) — used in `Main.java` for test mode shutdown delay to avoid blocking the main thread
- **Toolchain requirement** — enforced in `build.gradle.kts` via `JavaLanguageVersion.of(25)`

If adding new threads, prefer `Thread.startVirtualThread()` over traditional `new Thread()` for lightweight, scalable concurrency.

## JDA Best Practices

**Never use cache-only lookups** (e.g., `getUserById()`, `getMemberById()`, `getChannelById()`) — they only check local cache and return null if the entity isn't cached. Breaks when users leave, members go offline, or entities haven't been cached yet.

**Always use retrieval methods instead:**
- `jda.retrieveUserById(id).complete()` — fetches from Discord API if not cached
- `jda.retrieveMemberById(guildId, userId).complete()` — fetches member from API if not cached
- `guild.retrieveChannelById(id).complete()` — fetches channel from API if not cached

For async/non-blocking use (preferred in Discord event handlers):
- `.queue(success, failure)` — queue async fetch with success/failure callbacks
- `.complete()` — synchronous, blocks until response (use sparingly)

This ensures reliability even when entities aren't cached (e.g., resolving user info for actions targeting users who've left the server).
