# Modcord: AI-Powered Discord Moderation

[![GitHub Repo](https://img.shields.io/badge/repo-HoneyBerries%2FModcord-181717?logo=github)](https://github.com/HoneyBerries/Modcord)
[![Java 25+](https://img.shields.io/badge/java-25%2B-orange?logo=openjdk&logoColor=white)](https://openjdk.org/)
[![Gradle](https://img.shields.io/badge/build-Gradle-02303A?logo=gradle&logoColor=white)](https://gradle.org/)
[![Discord](https://img.shields.io/badge/platform-Discord-5865F2?logo=discord&logoColor=white)](https://discord.com/)
[![OpenAI-Compatible](https://img.shields.io/badge/AI-OpenAI--compatible-10A37F?logo=openai&logoColor=white)](https://platform.openai.com/docs/api-reference)
[![PostgreSQL](https://img.shields.io/badge/database-PostgreSQL-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![License](https://img.shields.io/badge/license-Custom-lightgrey)](https://github.com/HoneyBerries/Modcord/blob/main/LICENSE.md)

**Latest Version:** v3.2.0 | **Last Updated:** April 2026

---

## Table of Contents

- [What is Modcord?](#-what-is-modcord)
- [Why Modcord?](#-why-modcord)
- [How It Works](#-how-it-works)
- [Quick Start](#-quick-start)
- [Architecture](#-architecture)
- [Commands](#-commands)
- [Configuration](#-configuration)
- [Contributing](#-contributing)
- [License](#-license)
- [Support](#-support)

---

## 🤖 What is Modcord?

Modcord is an **AI-powered Discord moderation bot** that uses Large Language Models to understand conversation context and make intelligent moderation decisions—not just matching keywords.

Instead of flagging "fire" in #gaming (when the user meant it positively) or misunderstanding sarcasm and inside jokes, Modcord reads the **full conversation history** and applies server-specific rules with transparency.

### The Problem with Keyword Filtering

Traditional moderation bots rely on keyword lists:

- ❌ False positives (flagging innocent messages)
- ❌ Missing context (single-message analysis)
- ❌ No nuance (sarcasm, cultural references, tone)
- ❌ Opaque decisions (users don't understand why they were moderated)

### The Modcord Solution

- ✅ **Context-aware** — reads the last 10–20 messages to understand intent
- ✅ **Configurable per server** — define custom rules and channel guidelines
- ✅ **Transparent** — logs reasoning for every decision
- ✅ **Self-hostable** — run on your own infrastructure
- ✅ **OpenAI-compatible** — works with OpenAI, Ollama, and other LLM providers
- ✅ **Open source** — audit and modify the code yourself

**Result:** Smarter decisions, fewer false positives, and happier communities.

---

## 📊 Why Modcord?

| Feature | Modcord | Keyword Bots | Manual Mods |
|---------|---------|--------------|------------|
| **Context-Aware** | ✅ Full conversation | ❌ Single message | ✅ Full context |
| **Customizable** | ✅ Per-server rules | ✅ Yes | ✅ Yes |
| **Transparent** | ✅ Reasoning logged | ❌ No explanation | ✅ Yes |
| **Self-Hostable** | ✅ Your infrastructure | ❌ Cloud only | ✅ Yes |
| **Open Source** | ✅ MIT-style license | ❌ Proprietary | N/A |
| **LLM-Powered** | ✅ GPT-4, Ollama, etc. | ❌ No | N/A |
| **Setup Time** | ⏱️ 10 minutes | ⏱️ 5 minutes | N/A |
| **Cost** | 💰 LLM usage only | 💸 Free–Premium | 💸💸💸 Salary |

---

## 🏗️ How It Works

Modcord's moderation pipeline works in real-time as messages arrive:

1. **Message arrives** in Discord
2. **Batching** — recent messages are grouped together with a short delay to collect context efficiently
3. **Context gathering** — the bot fetches previous messages from the channel to understand the conversation
4. **Rule loading** — guild-specific rules and channel guidelines are retrieved from the database
5. **LLM querying** — the conversation history and rules are sent to the LLM (OpenAI, Ollama, etc.)
6. **Decision parsing** — the LLM response is parsed into a moderation decision
7. **Action execution** — the decision is applied (allow/delete/warn/timeout/kick/ban), and the user is notified
8. **Logging** — every decision is recorded in the database for auditing and appeals

If no action is needed, the message is simply allowed through. If a violation is detected, the bot executes the appropriate moderation action and posts a summary to the audit log channel.

---

## 🚀 Quick Start

### Prerequisites

- **Java 25+** (JDK 25 or newer)
- **PostgreSQL 14+**
- **Discord bot token** (from [Discord Developer Portal](https://discord.com/developers/applications))
- **OpenAI API key** or Ollama instance (for LLM inference)

### Clone the Repository

```bash
git clone https://github.com/HoneyBerries/Modcord.git
cd Modcord
```

### Set Up Environment Variables

```bash
cp .env.example .env
```

Edit `.env` and fill in your credentials:

```env
DISCORD_BOT_TOKEN=your_discord_bot_token
OPENAI_API_KEY=your_openai_api_key
POSTGRES_DB_PASSWORD=your_database_password
```

### Review Configuration

Main settings live in [`config/app_config.yml`](config/app_config.yml):

- PostgreSQL connection details
- AI endpoint URL and model name
- Moderation timing and context windows
- Default rules and channel guidelines
- Fallback behaviors

The system prompt is in [`config/system_prompt.md`](config/system_prompt.md).

### Run the Bot

```bash
# Run the bot
./gradlew run

# Or build an executable JAR
./gradlew assemble

# Run tests
./gradlew test

# Run a short test run (auto-shuts down after 5s)
./gradlew runTest
```

---

## 🏗️ Architecture

Modcord is built as a modular pipeline with clear separation of concerns:

- **Discord Integration** — Connects to Discord, registers commands, and listens for incoming messages
- **Message Batching** — Buffers messages per guild to collect context efficiently before processing
- **Context Gathering** — Fetches conversation history and server metadata from Discord and the database
- **Rule Management** — Loads guild-specific rules, channel guidelines, and exclusions from the database
- **LLM Interface** — Sends conversation context to an OpenAI-compatible LLM endpoint and parses responses
- **Action Execution** — Applies moderation decisions in parallel (delete messages, timeout, kick, ban, etc.)
- **Audit Logging** — Records all decisions to the database with reasoning for transparency and appeals

All configuration is stored in PostgreSQL, allowing server admins to customize rules and settings without code changes. The system is designed to be non-blocking so message processing doesn't slow down the Discord bot itself.

---

## 📝 Commands

### Core Commands

#### `/preferences` — Guild Configuration
Configure how the bot behaves in your server:
- `ai` — Enable or disable AI moderation for the guild
- `rules_channel` — Set the channel where server rules are posted
- `audit_channel` — Set the channel for moderation action logs
- `settings` — View current preferences and configuration

#### `/mod` — Manual Moderation Actions
Take direct moderation action against users:
- `warn` — Warn a user with a reason
- `timeout` — Timeout a user (1–40,320 minutes)
- `kick` — Kick a user from the server
- `ban` — Ban a user (1–365 days)
- `unban` — Unban a previously banned user

### Additional Commands

- `/status` — Check bot health, ping, uptime, and guild count
- `/exclude` — Exclude users, roles, or channels from AI moderation
- `/rollback` — Undo previous moderation actions
- `/appeal` — Appeal or review moderation decisions
- `/shutdown` — Gracefully shut down the bot

---

## ⚙️ Configuration

### `config/app_config.yml`

Main settings file with database, caching, moderation timing, and AI inference config:

```yaml
database:
  url: "jdbc:postgresql://host:port/database"
  username: "your_db_user"
  # Password loaded from POSTGRES_DB_PASSWORD env var

cache:
  rules_cache_refresh: 60                 # Seconds
  channel_guidelines_cache_refresh: 60    # Seconds

moderation:
  moderation_queue_duration: 30           # Seconds before processing batch
  num_history_context_messages: 50        # Messages to fetch for context
  history_context_max_age: 86400          # Max age in seconds

ai_settings:
  base_url: "https://your-api-endpoint/v1"
  model_name: "your-model-name"
  api_request_timeout: 3600               # Seconds

generic_server_rules: |
  1. Be respectful to other users and the server.
  2. No spamming.
  ...

generic_channel_guidelines: "No specific guidelines."
```

See [`config/app_config.yml`](config/app_config.yml) for the full configuration file.

### `config/system_prompt.md`

The system prompt guides the LLM on moderation philosophy and decision-making. Customize this to fit your community's values.

### Environment Variables (`.env`)

- `DISCORD_BOT_TOKEN` — Your Discord bot token
- `OPENAI_API_KEY` — OpenAI API key (or your LLM provider's key)
- `POSTGRES_DB_PASSWORD` — Database password

---

## 🧪 Testing

### Unit Tests

```bash
./gradlew test
```

### Integration Tests

Some tests require a live Discord bot connection and a test guild:

```bash
./gradlew test --include-group integration
```

Tests use JUnit `Assumptions` to skip gracefully if the bot isn't connected.

---

## 🚧 Current Scope

Modcord includes the core pieces of an AI moderation pipeline:

- ✅ Discord event ingestion and message batching
- ✅ Conversation history context handling
- ✅ Structured LLM output generation and parsing
- ✅ Database-backed configuration and audit logging
- ✅ Slash commands for health checks, preferences, and admin workflows
- ✅ Appeals and rollback capabilities
- ✅ Per-guild rules and per-channel guidelines

The project is actively developing; check GitHub for ongoing work.

---

## 🤝 Contributing

Contributions are welcome! See [`CONTRIBUTING.md`](CONTRIBUTING.md) for guidelines.

### Development Setup

```bash
git clone https://github.com/HoneyBerries/Modcord.git
cd Modcord

./gradlew dependencies
./gradlew test
./gradlew spotlessApply
```

---

## 🆘 Support

- **GitHub Issues** — [Report bugs or request features](https://github.com/HoneyBerries/Modcord/issues)
- **GitHub Discussions** — [Ask questions and discuss ideas](https://github.com/HoneyBerries/Modcord/discussions)
- **Email** — [henry.rainbowfish@gmail.com](mailto:henry.rainbowfish@gmail.com)

---

## 📄 License

Modcord uses a custom license rather than a standard OSI license. Personal, educational, non-profit, and evaluation use are allowed. Commercial use requires a separate license unless you qualify through contribution tiers.

See [`LICENSE.md`](LICENSE.md) for full terms.

---

## Stack

- **Java 25+**
- **Gradle** — build tool
- **JDA** — Discord Java library
- **PostgreSQL** — persistent storage
- **Liquibase** — schema migrations
- **OpenAI-compatible API** — LLM inference (GPT-4, Ollama, etc.)

---

## Previous Versions

For the previous Python-based version, check out the [`old-python-version` branch](https://github.com/HoneyBerries/Modcord/tree/old-python-version).

The current Java version (v3.2.0) is the main branch.
