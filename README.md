# Modcord

[![GitHub Repo](https://img.shields.io/badge/repo-HoneyBerries%2FModcord-181717?logo=github)](https://github.com/HoneyBerries/Modcord)
[![Java 25+](https://img.shields.io/badge/java-25%2B-orange?logo=openjdk&logoColor=white)](https://openjdk.org/)
[![Gradle](https://img.shields.io/badge/build-Gradle-02303A?logo=gradle&logoColor=white)](https://gradle.org/)
[![Discord](https://img.shields.io/badge/platform-Discord-5865F2?logo=discord&logoColor=white)](https://discord.com/)
[![OpenAI-Compatible](https://img.shields.io/badge/AI-OpenAI--compatible-10A37F?logo=openai&logoColor=white)](https://platform.openai.com/docs/api-reference)
[![PostgreSQL](https://img.shields.io/badge/database-PostgreSQL-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![License](https://img.shields.io/badge/license-Custom-lightgrey)](https://github.com/HoneyBerries/Modcord/blob/main/LICENSE.md)
[![GitHub stars](https://img.shields.io/github/stars/HoneyBerries/Modcord?style=social)](https://github.com/HoneyBerries/Modcord/stargazers)

Modcord is an AI-powered Discord moderation bot built for communities that want more context-aware moderation than simple keyword filters. It combines Discord event ingestion, configurable policy context, and an OpenAI-compatible inference layer to evaluate message batches and determine what moderation action should happen next.

The project is designed for self-hosting and experimentation. It uses PostgreSQL for persistence, Liquibase for schema management, and a configurable AI endpoint so you can point it at the model provider that fits your deployment.

## Why Modcord

- Moderates with conversation context instead of single-message checks
- Supports server rules and channel-specific guidance in the moderation flow
- Works with OpenAI-compatible inference endpoints, not just one provider
- Persists moderation state and configuration in PostgreSQL
- Ships as a Java/Gradle service that can be run directly

## How It Works

At a high level, Modcord listens to Discord message events, groups recent activity into moderation batches, enriches those batches with older context, and sends the result to an LLM using a structured output format. That output is then parsed into moderation decisions the bot can use downstream.

The architecture is intentionally straightforward:

- Discord/JDA handles gateway events and slash commands
- A processing layer batches messages and assembles context
- A policy layer injects generic and guild/channel-specific rules
- An inference layer sends structured moderation requests to an OpenAI-compatible endpoint
- PostgreSQL stores persistent data, with Liquibase managing schema changes

## Stack

- Java 25+
- Gradle
- JDA
- PostgreSQL
- Liquibase
- OpenAI-compatible chat completions API

## Quick Start

### Prerequisites

- Java 25 or newer
- PostgreSQL
- A Discord bot token
- An API key for your chosen OpenAI-compatible inference provider

### 1. Clone the repository

```bash
git clone https://github.com/HoneyBerries/Modcord.git
cd Modcord
```

### 2. Create your environment file

```bash
cp .env.example .env
```

Then set the required values in `.env`:

```env
DISCORD_BOT_TOKEN=your_discord_bot_token
OPENAI_API_KEY=your_inference_api_key
POSTGRES_DB_PASSWORD=your_database_password
```

### 3. Review the runtime config

Main runtime settings live in [`config/app_config.yml`](https://github.com/HoneyBerries/Modcord/blob/main/config/app_config.yml). This is where you configure:

- PostgreSQL connection details
- AI endpoint URL
- Model name
- Moderation timing and context windows
- Generic fallback rules and channel guidance

There is also a separate system prompt file at [`config/system_prompt.md`](https://github.com/HoneyBerries/Modcord/blob/main/config/system_prompt.md).

The default config currently points at specific hosted services, so you should replace those values for your own deployment before running the bot.

### 4. Run the bot

```bash
./gradlew run
```

To build a executable jar:

```bash
./gradlew build
```

To run the unit test suite:

```bash
./gradlew runTest
```

To run a runtime test:
```bash
./gradlew run
```

## Configuration

Modcord keeps most of its behavior configurable rather than hardcoding moderation assumptions. In practice, you will usually tune:

- The AI endpoint and model you want to use
- How long messages should be buffered before moderation
- How much older history should be included as context
- Default rules and guidelines when a guild has not defined its own

## Current Scope

Modcord already includes the core pieces for an AI moderation pipeline, but it still reads as an actively developing project rather than a finished platform. The current codebase includes:

- Discord event ingestion
- Message batching and history context handling
- Structured LLM output generation and parsing
- Database-backed configuration and moderation data
- Basic slash commands for health, ping, uptime, and admin/debug workflows

## Contributing

Contributions are welcome. See [`CONTRIBUTING.md`](https://github.com/HoneyBerries/Modcord/blob/main/CONTRIBUTING.md) for contribution notes.

## License

Modcord uses a custom license rather than a standard OSI license. Personal, educational, non-profit, and evaluation use are allowed, while commercial use requires a separate license unless you qualify through contribution tiers.

See [`LICENSE.md`](https://github.com/HoneyBerries/Modcord/blob/main/LICENSE.md) for the full terms.
