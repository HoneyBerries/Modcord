# Discord Moderation Bot (Modcord)

[![Run Tests](https://github.com/HoneyBerries/Modcord/actions/workflows/tests.yaml/badge.svg)](https://github.com/HoneyBerries/Modcord/actions/workflows/tests.yaml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Commit Activity](https://img.shields.io/github/commit-activity/m/honeyberries/modcord)](https://github.com/honeyberries/modcord/commits)
[![Chat on Discord](https://img.shields.io/badge/chat-on%20Discord-5865F2.svg)](https://discord.gg/c354AX236r)

## ❗ Alpha Stage ❗

This bot is currently in a very early alpha stage. It is buggy and may not work as expected. Use at your own risk.

## Features

-   **AI-Powered Moderation**: Uses a Large Language Model to analyze chat messages and suggest moderation actions.
-   **Slash Commands**: Provides a full suite of slash commands for manual moderation (warn, timeout, kick, ban).
-   **Contextual Analysis**: Maintains per-channel chat history to provide context to the AI model.
-   **Standardized Embeds**: Uses standardized and clear embeds for all moderation actions.
-   **Temporary Actions**: Supports temporary bans and timeouts with automatic removal.
-   **Robust Logging**:
    -   Detailed console and rotating file logs.
    -   Logs are stored in a root `logs/` directory.
    -   Centralized logger with per-module sub-loggers.
    # Modcord — Discord Moderation Bot

    Modcord is a Discord moderation assistant that leverages a local or hosted
    language model to detect and suggest moderation actions (warn, timeout,
    delete, kick, ban). It's designed for server operators who want a
    configurable, auditable, and extensible moderation pipeline.

    This repository contains the bot, small infrastructure helpers, and a
    pluggable AI engine layer.

    Highlights
    - AI-powered moderation with per-channel message batching.
    - Slash commands for manual actions and administration.
    - Per-guild settings and rules cache.
    - Structured logging with rotating files for production usage.

    Quick start
    1. Create a virtualenv and activate it:

    ```bash
    python -m venv .venv
    source .venv/bin/activate
    ```

    2. Install the project in editable mode:

    ```bash
    pip install -e .
    ```

    3. Add your Discord token to `.env`:

    ```text
    DISCORD_BOT_TOKEN=your_bot_token_here
    ```

    4. Run tests:

    ```bash
    python -m pytest -q
    ```

    5. Launch the bot locally:

    ```bash
    python -m modcord
    # or, after editable install
    modcord
    ```

    Configuration & architecture notes
    - The AI lifecycle helpers live in `modcord.ai.ai_lifecycle` (initialize/restart/shutdown).
    - Batching and per-guild persistence are handled by `modcord.configuration.guild_settings`.
    - Moderation orchestration is implemented in `modcord.ai.ai_moderation_processor` and the low-level model access is in `modcord.ai.ai_core`.
    - Cogs live under `src/modcord/bot/cogs`.

    Developer docs
    - See `DEVELOPMENT.md` for a concise local development guide.
    - See `message_batching.md` for the batching design and tuning ideas.

    Contributing
    - Open issues for bugs or design discussions.
    - Add tests for new behaviors and aim for small PRs with clear intentions.

    Security note
    - Never commit secrets. Use environment variables or CI secrets for tokens and keys.

    License & acknowledgements
    - This project is © the contributors. Include a license file if needed.
