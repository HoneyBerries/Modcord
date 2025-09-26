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

from modcord.ai.ai_model import MODEL_STATE, moderation_processor
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
        "modcord.bot.cogs.debug",
        "modcord.bot.cogs.moderation",
        "modcord.bot.cogs.events",
        "modcord.bot.cogs.settings",
    )


def load_cogs(discord_bot_instance: discord.Bot) -> None:
    """Load cogs by importing modules explicitly from the cogs package."""
    import inspect

    modules = []

    for module_path in discover_cog_modules():
        try:
            module = __import__(module_path, fromlist=["*"])
            modules.append(module)
        except Exception as exc:  # noqa: BLE001 - ensure all failures logged
            logger.error("Failed to import cog module %s: %s", module_path, exc, exc_info=True)

    for module in modules:
        mod_name = module.__name__
        try:
            # Prefer a Cog subclass if present
            cog_class = None
            for obj in vars(module).values():
                if inspect.isclass(obj) and issubclass(obj, discord.Cog) and obj is not discord.Cog:
                    cog_class = obj
                    break

            if cog_class:
                discord_bot_instance.add_cog(cog_class(discord_bot_instance))
                logger.info(f"Loaded cog: {cog_class.__name__} from {mod_name}")
                continue

            logger.error(f"No Cog subclass found in {mod_name}; skipping.")
        except Exception as e:
            logger.error(f"Failed to load cog {mod_name}: {e}", exc_info=True)


async def initialize_ai_model() -> None:
    try:
        logger.info("Initializing AI model before bot startup…")
        await moderation_processor.init_model()
        await moderation_processor.start_batch_worker()
        if MODEL_STATE.init_error and not MODEL_STATE.available:
            logger.critical("AI model failed to initialize: %s", MODEL_STATE.init_error)
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
        if MODEL_STATE.init_error:
            logger.critical("AI initialization failed irrecoverably: %s", MODEL_STATE.init_error)
        raise

    if not MODEL_STATE.available:
        logger.warning(
            "AI model is unavailable (%s). Continuing without automated moderation.",
            MODEL_STATE.init_error or "no details",
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
