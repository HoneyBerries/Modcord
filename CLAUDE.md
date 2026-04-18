# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the bot
./gradlew run

# Run with --test flag (auto-shuts down after 5 seconds)
./gradlew runTest

# Build a fat/shadow JAR
./gradlew assemble

# Run unit tests
./gradlew test
```

## Environment Setup

Copy `.env.example` to `.env` and fill in:

```
DISCORD_BOT_TOKEN=...
OPENAI_API_KEY=...
POSTGRES_DB_PASSWORD=...
```

Runtime config lives in `config/app_config.yml` (AI endpoint, model name, moderation timing, context windows, fallback rules). The system prompt is in `config/system_prompt.md`.

## Architecture

Modcord is an AI-powered Discord moderation bot. Java 25, Gradle, JDA, PostgreSQL (via HikariCP), Liquibase for schema migrations, and an OpenAI-compatible inference client.

### Startup flow (`Main.java`)

1. `Database.initialize(AppConfig)` — opens HikariCP pool, runs Liquibase migrations
2. `JDAManager.getInstance()` — connects to Discord, registers all slash commands and event listeners
3. Scheduled tasks start: `UnbanWatcherTask`, `GuildRulesTask`, `ChannelGuidelinesTask`

### Message processing pipeline

The core flow is message → batch → AI → action:

1. **`MessageListener`** receives Discord message events and calls `GlobalOrchestrationService.addMessage()`
2. **`GlobalOrchestrationService`** (singleton) maintains per-guild queues and schedules a delayed processing run per guild, coalescing rapid arrivals into a single batch. Prevents concurrent processing of the same guild via an in-flight set.
3. **`GuildMessageProcessingService`** (one per guild, lazily created) manages the actual queue with arrival timestamps. When `runPipeline()` is called:
   - Gets queued messages (current window)
   - Fetches historical context from Discord via `HistoryFetcher`
   - Builds `GuildModerationBatch` with `ModerationUser` objects (user details, roles, per-channel message lists)
   - Generates a dynamic JSON schema via `DynamicSchemaGenerator` (constrains AI output to actual users/channels in the batch)
   - Builds the dynamic system prompt via `DynamicSystemPrompt` (injects guild-specific rules and channel guidelines from DB)
   - Calls `InferenceEngine.generateResponse()` (async, OpenAI SDK)
   - Parses the JSON response via `ActionDataJSONParser` into `ActionData` objects
   - Logs to DB (`AILogRepository`, `GuildModerationActionsRepository`)
   - Executes actions in parallel via `ActionHandler`
4. **`ActionHandler`** (singleton) executes each `ActionData`: sends user DM → deletes flagged messages → applies moderation action (timeout/kick/ban/unban) → posts to audit log channel

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

`AppConfigTest` — unit tests against `config/app_config.yml`, no external dependencies.

`TestActionHandler` — integration tests tagged `@Tag("integration")` that require a live Discord bot connection and a real test guild (hardcoded IDs). They use JUnit `Assumptions` to skip gracefully if the bot isn't connected.
