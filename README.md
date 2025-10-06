# Modcord — Discord Moderation Bot

[![Run Tests](https://github.com/HoneyBerries/Modcord/actions/workflows/tests.yaml/badge.svg)](https://github.com/HoneyBerries/Modcord/actions/workflows/tests.yaml)
[![Coverage](https://codecov.io/gh/HoneyBerries/Modcord/branch/main/graph/badge.svg?token=YOUR_CODECOV_TOKEN)](https://codecov.io/gh/HoneyBerries/Modcord)
[![License: Modcord Custom License](https://img.shields.io/badge/license-Modcord%20Custom%20License-blue.svg)](LICENSE)
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

- Python 3.12+
- A virtual environment tool (e.g., `venv`)

### Installation

1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/HoneyBerries/Modcord.git
    cd modcord
    ```

2.  **Create and Activate a Virtual Environment**:
    ```bash
    python -m venv venv
    source venv/bin/activate
    ```

3.  **Install Dependencies**:
    This command installs all necessary packages, including the project itself in editable mode.
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Your Bot Token**:
    Create a file named `.env` in the project's root directory and add your Discord bot token:
    ```
    DISCORD_BOT_TOKEN=your_discord_bot_token_here
    ```

5.  **Run the Bot**:
    ```bash
    # Run directly via the Python module
    python -m modcord

    # Or use the console script
    modcord
    ```

---

## Features

- **AI-Powered Moderation**: Uses a local or hosted Large Language Model to analyze messages and suggest moderation actions.
- **Slash Commands**: A full suite of commands for manual moderation (`warn`, `timeout`, `kick`, `ban`).
- **Contextual Analysis**: Maintains per-channel message history for accurate AI moderation suggestions.
- **Temporary Actions**: Supports temporary bans and timeouts with automatic removal.
- **Standardized Embeds**: Clear and consistent embeds for all moderation actions.
- **Robust Logging**: Features console and rotating file logs stored in the `logs/` directory.
- **Per-Guild Settings**: Customizable settings and rules for each server.
- **Extensible Architecture**: A modular design with a pluggable AI engine layer.

---

## Configuration & Architecture

- **AI Lifecycle**: `modcord.ai.ai_lifecycle` (initialize/restart/shutdown).
- **Configuration & Persistence**: `modcord.configuration.guild_settings`.
- **Moderation Orchestration**: `modcord.ai.ai_moderation_processor` and `modcord.ai.ai_core`.
- **Cogs**: Located under `src/modcord/bot/cogs`.

---

## Contributing

We welcome contributions! Please see [`CONTRIBUTING.md`](CONTRIBUTING.md) for detailed instructions on how to get involved, including our development guide and contributor benefits.

- Open an issue for bugs or design discussions.
- Submit small, focused PRs with clear intentions.
- Add tests for any new functionality.

---

## Security

- **Never commit secrets**. Use environment variables or CI secrets for tokens and keys. The `.env` file is included in `.gitignore` to prevent accidental commits.

---

## License

This project is © the contributors. See [LICENSE](LICENSE) for details.

---

## Join the Community

- Chat with us on [Discord](https://discord.gg/c354AX236r) for support and discussions.