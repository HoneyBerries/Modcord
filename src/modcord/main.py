"""
Discord Moderation Bot
======================

A Discord bot that uses an AI model to moderate chat, handle rule violations,
and provide server administration commands for manual moderation actions like
banning, kicking, and timing out users.

Refactored version using cogs for better organization and maintainability.
"""

import os
import sys
from pathlib import Path
from typing import Iterable
import asyncio
import discord
from dotenv import load_dotenv

from modcord.ai.ai_model import model_state, moderation_processor
from modcord.util.logger import get_logger, handle_exception


# Set the base directory to the project root
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Get logger for this module
logger = get_logger("main")


def load_environment() -> str | None:
    """Load environment variables and return the Discord bot token."""
    load_dotenv(dotenv_path=BASE_DIR / ".env")
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        logger.critical("'DISCORD_BOT_TOKEN' environment variable not set. Bot cannot start.")
    return token


def build_intents() -> discord.Intents:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.messages = True
    intents.reactions = True
    intents.members = True
    return intents


def discover_cog_modules() -> Iterable[str]:
    return (
        "modcord.bot.cogs.debug_cmds",
        "modcord.bot.cogs.events",
        "modcord.bot.cogs.guild_settings_cmds",
        "modcord.bot.cogs.moderation_cmds",
    )


def load_cogs(discord_bot_instance: discord.Bot) -> None:
    """Load cogs by importing modules explicitly from the cogs package."""
    from modcord.bot.cogs import debug_cmds, events, guild_settings_cmds, moderation_cmds

    debug_cmds.setup(discord_bot_instance)
    events.setup(discord_bot_instance)
    guild_settings_cmds.setup(discord_bot_instance)
    moderation_cmds.setup(discord_bot_instance)
    logger.info("All cogs loaded successfully.")

async def initialize_ai_model() -> None:
    try:
        logger.info("Initializing AI model before bot startup…")
        await moderation_processor.init_model()
        await moderation_processor.start_batch_worker()
        if model_state.init_error and not model_state.available:
            logger.critical("AI model failed to initialize: %s", model_state.init_error)
    except Exception as exc:  # noqa: BLE001 - surface initialization failures
        logger.critical("Unexpected error during AI initialization: %s", exc, exc_info=True)
        raise


async def start_bot(token: str) -> None:
    bot = discord.Bot(intents=build_intents())
    load_cogs(bot)

    logger.info("Attempting to connect to Discord…")
    try:
        await bot.start(token)
    finally:
        logger.info("Discord bot shutdown sequence complete.")


async def async_main() -> None:
    token = load_environment()
    if not token:
        raise SystemExit(1)

    try:
        await initialize_ai_model()
    except Exception:
        if model_state.init_error:
            logger.critical("AI initialization failed irrecoverably: %s", model_state.init_error)
        raise

    if not model_state.available:
        logger.warning(
            "AI model is unavailable (%s). Continuing without automated moderation.",
            model_state.init_error or "no details",
        )

    await start_bot(token)


def main() -> None:
    """Synchronous entrypoint that delegates to the async runner."""
    logger.info("Starting Discord Moderation Bot…")
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user.")
    except SystemExit as exit_exc:
        raise exit_exc
    except Exception as exc:
        logger.critical("An unexpected error occurred while running the bot: %s", exc, exc_info=True)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    # Set the global exception hook to use the custom handler
    sys.excepthook = handle_exception
    main()
