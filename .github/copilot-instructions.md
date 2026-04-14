# Copilot Instructions for Modcord

## Before You Code

**Surface assumptions. Ask for clarification before implementing.**

1. **State assumptions explicitly.** If the request is ambiguous, ask—don't guess.
2. **Present tradeoffs.** If multiple approaches exist, lay them out. Let the human choose.
3. **Push back on scope.** If the request seems overcomplicated or vague, say so.
4. **Stop if confused.** Name what's unclear. Don't code your way out of confusion.

## During Implementation

### Simplicity First

- **Minimum code that solves the problem.** No speculative features, no flexibility that wasn't asked for.
- **No abstractions for single-use code.** Avoid premature over-engineering.
- **No error handling for impossible scenarios.**
- If you write 200 lines and it could be 50, rewrite it.

### Surgical Changes

- **Touch only what you must.** Every changed line should trace back to the user's request.
- **Match existing style**, even if you'd do it differently.
- **Don't "improve" unrelated code**, comments, or formatting.
- **Clean up your own mess.** Remove imports/variables/functions that *your changes* made unused. Don't remove pre-existing dead code.

### Goal-Driven Execution

**Define success criteria before and after each change.**

- State a brief plan: `[Step] → verify: [check]`
- Loop until verified. A change isn't done until you've checked it works.
- After configuration changes (package.json, .env, gradle.kts): apply them (`npm install`, `pip install`, `./gradlew build`)
- After starting a process: verify it's running and responsive.

## Build, Test, and Lint

### Prerequisites
- **Java 25+** (required; build will fail with earlier versions)
- **PostgreSQL** (for runtime and integration tests)
- Environment variables in `.env` (copy from `.env.example`)

### Key Commands

```bash
# Build the application (compiles and creates JAR)
./gradlew assemble

# Run the bot normally
./gradlew run

# Run the bot with auto-shutdown after 5 seconds (for testing)
./gradlew runTest

# Run all unit tests (JUnit 5)
./gradlew test

# Run a specific test class
./gradlew test --tests "net.honeyberries.ai.InferenceEngineTest"

# Run a specific test method
./gradlew test --tests "net.honeyberries.ai.InferenceEngineTest.testGetInstanceReturnsSingleton"

# Build a fat JAR (shadowJar task)
./gradlew shadowJar
```

## High-Level Architecture

Modcord is an AI-powered Discord moderation bot that processes messages in context-aware batches. The architecture follows a **layered orchestration pattern**:

### Core Layers

1. **Discord Gateway (JDA)**
   - Handles real-time message events via `MessageListener`
   - Processes slash commands through handler classes in `discord/slashCommands/`
   - Manages bot state and Discord API interactions

2. **Message Processing Pipeline**
   - `GlobalOrchestrationService` coordinates per-guild processing pipelines
   - `GuildMessageProcessingService` implements the 8-step moderation pipeline:
     1. Message arrival and queueing
     2. Time-windowed batch coalescing (messages grouped within a configured window)
     3. Historical context fetching from database
     4. Policy injection (guild-specific rules and channel guidelines)
     5. Structured AI inference via OpenAI-compatible API
     6. Output parsing into moderation decisions
     7. Parallel action application (mutes, bans, warn logs)
     8. In-flight tracking to prevent concurrent processing of the same guild

3. **AI Inference**
   - `InferenceEngine` provides async interface to OpenAI-compatible models
   - `DynamicSchemaGenerator` builds JSON schemas for structured outputs
   - `GuildModerationBatchToAIInput` assembles moderation context and policy into prompts
   - Results parsed into `ModerationDecision` objects via `ActionDataJSONParser`

4. **Data Persistence**
   - PostgreSQL database with Liquibase schema management (`db/changelog/`)
   - Repository pattern: `GuildRulesRepository`, `GuildPreferencesRepository`, `ChannelGuidelinesRepository`, etc.
   - Configuration driven: `config/app_config.yml` (AI endpoint, timing) and `config/system_prompt.md` (LLM instructions)

5. **Background Tasks**
   - `GuildRulesTask`, `ChannelGuidelinesTask` for periodic syncs
   - `UnbanWatcherTask` for expiring moderation actions

### Data Flow

```
Discord Event → MessageListener → GlobalOrchestrationService
  → GuildMessageProcessingService (per-guild queue)
  → ActionHandler (applies actions: mute, ban, warn)
  → InferenceEngine (async call to AI)
  → AILogRepository (logs results)
```

## Key Conventions

### Null Safety & Type Annotations
- All public APIs use `@NotNull`/`@Nullable` from `org.jetbrains.annotations`
- Defensive checks: `Objects.requireNonNull()` for all @NotNull parameters
- ~440+ null-safety annotations across the codebase

### Javadoc Standards
- **All public classes** require class-level Javadoc (2-4 sentences explaining purpose)
- **All public methods** need Javadoc with `@param`, `@return`, `@throws` tags
- **Override methods** (e.g., `onSlashCommandInteraction`) must document triggers and side effects
- **Field documentation** for important class members, especially those exposed in public APIs

### Slash Command Handlers
- Extend `ListenerAdapter` and override `onSlashCommandInteraction()`
- Register command structure in `updateCommands()` method
- Use `@NotNull`/`@Nullable` annotations on parameters and return types
- Add defensive null checks using `Objects.requireNonNull()`
- Example: `DebugCommands.java`, `ModerationCommands.java`, `StatusCommands.java`

### Singleton Pattern
- `GlobalOrchestrationService`, `InferenceEngine`, and other critical services use singleton pattern with `getInstance()`
- Initialize expensive resources lazily during first access

### Service Orchestration
- `GlobalOrchestrationService` maintains per-guild queues in `ConcurrentHashMap`
- Per-guild processing services (`GuildMessageProcessingService`) handle isolated moderation pipelines
- Scheduled futures prevent duplicate processing via `guildsInFlight` set
- Graceful shutdown: cancel pending runs and drain queues

### Configuration Loading
- Build script (`build.gradle.kts`) loads `.env` file at project root for secrets
- `AppConfig` loads `app_config.yml` for runtime settings (AI endpoint, model, timing windows)
- Environment variables are injected into Liquibase tasks for database management

### Testing
- Use JUnit 5 with `@Nested` and `@DisplayName` for readable test organization
- Some tests (e.g., `InferenceEngineTest`) are `@Disabled` and require external API credentials
- Test classes: `net.honeyberries.*.Test` (e.g., `AppConfigTest`, `InferenceEngineTest`, `TestActionHandler`)

### Naming Conventions
- Data types (wrappers): `GuildID`, `MessageID`, `ChannelID` (strongly typed identifiers)
- Repositories: `*Repository` suffix (e.g., `GuildRulesRepository`)
- Services: `*Service` suffix (e.g., `GlobalOrchestrationService`)
- Listeners: `*Listener` suffix (e.g., `MessageListener`)
- Slash command handlers: `*Command` or `*Commands` suffix (e.g., `DebugCommands`)
- Package structure: `net.honeyberries.*` with subpackages by layer (discord, database, services, ai, etc.)

### Package Organization
- `discord/` - JDA integration, listeners, slash commands
- `database/` - Repository classes and Database connection pooling
- `services/` - Orchestration and message processing pipelines
- `ai/` - Inference engine and schema generation
- `datatypes/` - DTOs and domain objects (strongly typed identifiers, preferences, actions)
- `config/` - Configuration loading and parsing
- `action/` - Moderation action handlers (mute, ban, etc.)
- `util/` - Utilities (token management, parsing helpers)

### Important Implementation Details
- Message batching uses concurrent queues with time windows (configurable in `app_config.yml`)
- In-flight tracking prevents concurrent moderation of the same guild during processing
- Async/await pattern with `CompletableFuture` for AI inference (non-blocking)
- Virtual threads for background tasks (Java 21+ feature)
- Structured JSON output from LLM parsed into strongly typed `ModerationDecision` objects
