# Repository Guidelines

## Project Structure & Module Organization

Modcord is a Java 25 Gradle project. Production code lives in `src/main/java/net/honeyberries`, grouped by responsibility: Discord integration in `discord`, moderation flow in `services`, AI interaction in `ai`, database access in `database/repository`, commands in `discord/slashCommands`, and shared value types in `datatypes`. Tests mirror the package layout under `src/test/java/net/honeyberries`. Runtime resources are in `src/main/resources`, including `app_config.yml`, `system_prompt.md`, Logback config, and Liquibase migrations under `db/changelog`. Root-level `config/` contains editable deployment configuration, and `examples/` contains sample AI output.

## Build, Test, and Development Commands

Use the Gradle wrapper so builds use the repository-pinned Gradle version.

```bash
./gradlew test        # Run JUnit 5 tests
./gradlew run         # Start the bot normally
./gradlew runTest     # Start with --test; auto-shuts down after 5 seconds
./gradlew assemble    # Build project artifacts
./gradlew shadowJar   # Build executable fat JAR with net.honeyberries.Main
```

On Windows PowerShell, use `.\gradlew.bat test` or the matching task name.

## Coding Style & Naming Conventions

Use Java conventions: 4-space indentation, `PascalCase` classes, `camelCase` methods and fields, and package names under `net.honeyberries`. Keep modules focused on their current responsibilities instead of adding cross-cutting helpers prematurely. Repository classes should stay in `database/repository`; Discord slash command handlers belong in `discord/slashCommands`; UI embed builders belong in `ui`. Prefer explicit domain types such as `GuildID`, `ChannelID`, and `ActionData` over raw strings or maps when the type already exists.

## Testing Guidelines

Tests use JUnit Jupiter. Name test classes with the existing `Test...` pattern, for example `TestGuildRulesRepo`, and place them in the matching package under `src/test/java`. Run `./gradlew test` before submitting changes. Some integration-style tests may depend on credentials, PostgreSQL, or Discord connectivity; guard new environment-dependent tests with JUnit assumptions so local test runs can skip cleanly.

## Commit & Pull Request Guidelines

Recent commits use short, imperative summaries such as `Update workflows` or `Add GEMINI.md documentation and release workflow`. Keep the first line concise and describe the user-visible change. Pull requests should include a brief summary, test results, linked issues when applicable, and screenshots or command output for Discord UI or workflow changes. Note any required config, migration, or `.env.example` updates.

## Security & Configuration Tips

Never commit `.env`, tokens, API keys, database passwords, or log files. Update `.env.example` when adding required environment variables. Review Liquibase changes in `src/main/resources/db/changelog` carefully and add new migrations instead of editing applied ones.
