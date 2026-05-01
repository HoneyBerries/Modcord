# Modcord - AI-Powered Discord Moderation

Modcord is a sophisticated Discord moderation bot that leverages Large Language Models (LLMs) to provide context-aware moderation. It goes beyond simple keyword filtering by analyzing conversation history and applying server-specific rules.

## Technical Stack

- **Runtime:** Java 25+ (utilizes virtual threads)
- **Build System:** Gradle
- **Discord Library:** JDA (Java Discord API)
- **AI Integration:** OpenAI-compatible Java SDK
- **Database:** PostgreSQL with HikariCP connection pooling
- **Migrations:** Liquibase
- **Configuration:** YAML (SnakeYAML) and .env (Dotenv)
- **Logging:** SLF4J with Logback

## Key Architectural Components

### Core Services (Singletons)
- **`Main`**: Entry point. Initializes database, Discord bot, and background tasks.
- **`Database`**: Wraps HikariCP. Handles SQL execution and transactions.
- **`JDAManager`**: Manages the JDA instance, command registration, and event listeners.
- **`GlobalOrchestrationService`**: Coordinates per-guild message queues. Coalesces rapid message arrivals into batches for efficient AI processing.
- **`InferenceEngine`**: Interface for LLM interaction. Supports structured JSON output using schemas.
- **`ActionHandler`**: Executes moderation decisions (deletions, timeouts, kicks, bans) and logs them.
- **`PreferencesManager`**: Manages guild-specific settings like rules and enabled features.

### Data Model
- **ID Wrappers (`net.honeyberries.datatypes.discord`)**: Strongly typed wrappers for Discord snowflakes (`UserID`, `GuildID`, `ChannelID`, etc.) to prevent ID mixing.
- **Domain Objects (`net.honeyberries.datatypes.action`, `net.honeyberries.datatypes.content`)**: Immutable records and classes for moderation actions (`ActionData`) and AI-ready content (`GuildModerationBatch`).

### Processing Pipeline
1. **Event Ingestion**: `MessageListener` -> `GlobalOrchestrationService`.
2. **Batching**: Messages are queued per guild with a configurable delay (default 30s) to collect context.
3. **Context Enrichment**: Fetches historical messages and guild rules/guidelines.
4. **AI Inference**: Sends structured context to the LLM; receives JSON-formatted moderation decisions.
5. **Action Execution**: `ActionHandler` processes decisions in parallel, notifying users and logging actions.

## Development Workflow

### Building and Running
- **Run the bot:** `./gradlew run`
- **Short test run (5s auto-shutdown):** `./gradlew runTest`
- **Build executable JAR:** `./gradlew assemble` (outputs to `build/libs/Modcord-all.jar` via ShadowJar)
- **Database migrations:** Managed via Liquibase (see `src/main/resources/db/changelog/`)

### Testing
- **Run unit tests:** `./gradlew test`
- **Integration tests:** Tagged with `@Tag("integration")`. These require a live Discord connection and specific environment variables. Use `Assumptions` to skip if credentials are missing.

### Environment Setup
1. Copy `.env.example` to `.env`.
2. Configure `DISCORD_BOT_TOKEN`, `OPENAI_API_KEY`, and `POSTGRES_DB_PASSWORD`.
3. Adjust application settings in `config/app_config.yml`.

## Engineering Standards & Conventions

### JDA Best Practices
- **NEVER use cache-only lookups** like `jda.getUserById()`. These return `null` if the entity is not in memory.
- **ALWAYS use retrieval methods**: `jda.retrieveUserById(id).complete()` or `.queue()`. This ensures the bot fetches data from the Discord API if needed.

### Code Style
- **Null Safety**: Use `@NotNull` and `@Nullable` annotations consistently.
- **Type Safety**: Use the custom ID wrappers (`UserID`, etc.) instead of raw `long`s for Discord IDs.
- **Concurrency**: Prefer virtual threads for lightweight async tasks. Use `GlobalOrchestrationService`'s patterns for thread-safe state management.
- **Documentation**: Provide detailed Javadoc for all public classes and non-trivial methods.

### Configuration
- All runtime settings should be defined in `config/app_config.yml` and accessed via `AppConfig.getInstance()`.
- The AI system prompt is stored in `config/system_prompt.md`.
