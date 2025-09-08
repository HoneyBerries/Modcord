# Discord Moderation Bot

This is a Discord bot that uses a Large Language Model to moderate a Discord server. It features AI-powered moderation, manual slash commands, and a robust, production-ready logging system.

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
    -   Optional structured (JSON) logging for production.
    -   Centralized logger with per-cog sub-loggers.
    -   Full traceback logging for all errors.

## Prerequisites

-   Python 3.10 or higher.
-   A Discord Bot Token with the required intents. You can get one from the [Discord Developer Portal](https://discord.com/developers/applications).

## Setup

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd <repository-directory>
    ```

2.  **Install dependencies:**
    It is recommended to use a virtual environment.
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    pip install -r requirements.txt
    ```

3.  **Create a `.env` file:**
    Create a file named `.env` in the root of the project and add your bot token. You can copy the example file:
    ```bash
    cp .env.example .env
    ```
    Then, open the `.env` file and replace the placeholder with your actual bot token:
    ```
    Mod_Bot_Token=YOUR_DISCORD_BOT_TOKEN_HERE
    ```

## Running the Bot

To run the bot, simply execute the `bot.py` script:

```bash
python main.py
```

## Configuration

### Logging

The logging system can be configured with the following environment variable:

-   `LOG_JSON_FORMAT`: Set to `true` to enable structured JSON logging. This is recommended for production environments where logs are sent to a log aggregation service.
    ```
    # .env file
    LOG_JSON_FORMAT=true
    ```

## Testing

This project includes a full suite of unit tests. To run the tests, use the provided `run_tests.py` script:

```bash
python RUN_ALL_TESTS.py
```

## Project Structure

```
.
├── cogs/           # Contains the cogs (plugins) for the bot.
├── data/           # Data files, such as config.yml.
├── logs/           # Directory for log files (created automatically).
├── tests/          # Unit tests for the project.
├── .env.example    # Example environment file.
├── bot.py          # Main entry point for the bot.
├── logger.py       # The logging system module.
├── requirements.txt # Project dependencies.
└── run_tests.py    # Script to run all unit tests.
```


## Source Layout and Entrypoint

- Authoritative modules live at the repository root (bot.py, ai_model.py, bot_helper.py, actions.py, logger.py, config_loader.py, bot_config.py, and cogs/).
- Use bot.py as the main entrypoint: `python bot.py`.
- The src/ directory contains legacy duplicates retained temporarily for reference; production code and tests do not import from src/. Prefer the root-level modules for any development.

## Testing Coverage

This project includes comprehensive unit tests that verify real functionality.
- AI model parsing and action selection (tests/test_ai_model.py)
- Cog behaviors and event handling with proper mocking (tests/test_bot.py)
- Helper utilities for moderation flows (tests/test_bot_helper.py)
- Configuration loading, rules precedence, and prompt formatting (tests/test_config_loader.py)
- Logging setup and file output via rotating handler (tests/test_logger.py)

Run the full suite:

```bash
python RUN_ALL_TESTS.py
```
