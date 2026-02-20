# Modcord — Discord Moderation Bot

[![Build](https://github.com/HoneyBerries/Modcord/actions/workflows/build.yaml/badge.svg)](https://github.com/HoneyBerries/Modcord/actions/workflows/build.yaml)
[![License: Modcord Custom License](https://img.shields.io/badge/license-Modcord%20Custom%20License-blue.svg)](LICENSE.md)
[![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Commit Activity](https://img.shields.io/github/commit-activity/m/honeyberries/modcord)](https://github.com/honeyberries/modcord/commits)
[![Chat on Discord](https://img.shields.io/badge/chat-on%20Discord-5865F2.svg)](https://discord.gg/c354AX236r)

---

## Overview

**Modcord** is a production-ready Discord moderation bot designed to help server operators maintain a safe and well-managed community. It leverages AI-powered moderation alongside traditional moderation tools to provide automated, contextual, and auditable moderation actions.

---

## Getting Started

Follow these steps to get Modcord running on your local machine for development or testing.

### Prerequisites

- Python 3.12.x
- A Discord bot token (create one at the [Discord Developer Portal](https://discord.com/developers/applications))
- An OpenAI-compatible API key and model endpoint

### Quick Start

1. **Clone the Repository**:
    ```bash
    git clone https://github.com/HoneyBerries/Modcord modcord
    cd modcord
    ```

2. **Configure Your Bot Token**:
    Create a file named `.env` in the project's root directory and add your Discord bot token:
    ```
    DISCORD_BOT_TOKEN=your_discord_bot_token_here
    ```

3. **Run the Program**:
    ```bash
    ./start.sh
    ```

The `start.sh` script will automatically:
- Detect or create a Python virtual environment
- Install all required dependencies from `requirements.txt`
- Launch the bot

No manual setup of a virtual environment or dependency installation is required—just run `./start.sh` and follow the prompts.

---

## Features

- **AI-Powered Moderation**: Uses an OpenAI-compatible API to analyze messages and suggest moderation actions.
- **Manual Slash Commands**: A full suite of commands for manual moderation (`warn`, `timeout`, `kick`, `ban`) and other management commands.
- **Contextual Analysis**: Pulls per-channel message history on demand to keep moderation context up to date.
- **Temporary Actions**: Supports temporary bans and timeouts.
- **Nice-looking Embeds**: Clear and consistent embeds for moderation actions and other commands.
- **Per-Guild Settings**: Customizable settings and rules for each server.
- **Extensible Architecture**: A modular design with a pluggable AI engine layer.

---

## Configuration & Architecture

- **AI Calls**: `modcord.ai.ai_moderation_processor` sends OpenAI-compatible chat requests (no local model lifecycle).
- **Configuration & Persistence**: `modcord.configuration.guild_settings` (using SQLite database at `data/app.db`).
- **Database**: Guild settings are stored in SQLite database for reliability and performance.
- **Moderation Orchestration**: `modcord.ai.ai_moderation_processor`.
- **Cogs**: Located under `src/modcord/bot/cogs`.

---

## Data Storage

Modcord uses SQLite to store guild-specific settings persistently. The database is automatically created on first run and stored at `data/app.db`.

### Database Schema

The `guild_settings` table stores per-guild configuration:
- `guild_id`: Discord guild/server ID (primary key)
- `ai_enabled`: Whether AI moderation is enabled (default: true)
- `rules`: Custom server rules for the AI to enforce
- `auto_*_enabled`: Flags for each moderation action type (warn, delete, timeout, kick, ban)
- `created_at`, `updated_at`: Timestamps for record tracking

The database uses Write-Ahead Logging (WAL) mode for better concurrency and includes automatic timestamp updates via triggers.

---

## Contributing

We welcome contributions! Please see [`CONTRIBUTING.md`](CONTRIBUTING.md) for detailed instructions on how to get involved, including our development guide and contributor benefits.

- Open an issue for bugs or design discussions.
- Submit small, focused PRs with clear intentions.
- Add tests for any new functionality.

---

## Security

- **Never show people your secrets**. Use environment variables or CI secrets for tokens and keys. The `.env` file is included in `.gitignore` to prevent accidental commits.

---

## License

This project is copyright (c) HoneyBerries. See [LICENSE](LICENSE.md) for details.

---

## Join the Community

- Chat with us on [Discord](https://discord.gg/c354AX236r) for support and discussions.
