# Discord Moderation Bot (Modcord)

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
    -   Logs are stored in a root `logs/` directory.
    -   Centralized logger with per-module sub-loggers.
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
    pip install -e .
    ```
    This will install the project in editable mode and all dependencies from `setup.py`.

3.  **Create a `.env` file:**
    Create a file named `.env` in the root of the project and add your bot token. You can copy the example file:
    ```bash
    cp .env.example .env
    ```
    Then, open the `.env` file and replace the placeholder with your actual bot token:
    ```
    DISCORD_BOT_TOKEN=YOUR_DISCORD_BOT_TOKEN_HERE
    ```

## Running the Bot

To run the bot, use the following command from the project root:

```bash
python -m main.py
```
Alternatively, since the project is installed with an entry point, you can use:
```bash
modcord
```

## Testing

This project includes a full suite of unit tests. To run the tests, use the standard Python `unittest` module from the project root:

```bash
python -m unittest discover tests
```

## Project Structure

The project follows a standard `src` layout for packaging and distribution.

```
my_project_root/
├── src/
│   └── modcord/
│       ├── __init__.py
│       ├── main.py         # Main entry point
│       ├── ai_model.py
│       ├── bot_helper.py
│       └── cogs/
│           ├── __init__.py
│           ├── general.py
│           └── ...
├── tests/
│   ├── __init__.py
│   ├── test_ai_model.py
│   └── ...
├── data/
│   └── config.yml          # Bot configuration
├── logs/
│   └── ...                 # Log files are generated here
├── setup.py                # Packaging script
├── requirements.txt        # Project dependencies
├── .env.example
└── README.md
```
