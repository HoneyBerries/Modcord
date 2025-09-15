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

import discord
from dotenv import load_dotenv
import asyncio

# Import AI model initializer to ensure model is available before bot starts
from modcord.ai_model import init_ai_model, MODEL_STATE

from modcord.logger import get_logger, handle_exception

# Set the base directory to the project root
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Get logger for this module
logger = get_logger("main")

# ==========================================
# Global Variables and Setup
# ==========================================
discord_bot_instance = None  # Global bot instance


# Test logging system
def test_all_logging_levels():
    """Test logging at all levels."""
    logger.debug("Debug logging initialized.")
    logger.info("Info logging initialized.")
    logger.warning("Warning logging initialized.")
    logger.error("Error logging initialized.")
    logger.critical("Critical logging initialized.")


# Load environment variables from the .env file in the project root
load_dotenv(dotenv_path=BASE_DIR / ".env")
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')


# ==========================================
# Cog Loading
# ==========================================
def load_cogs(discord_bot_instance):
    """Load cogs by importing modules explicitly from the cogs package."""
    import inspect

    try:
        # Explicit imports so linters/static analyzers can see them easily:
        from modcord.cogs import debug, moderation, events, general, settings
        modules = [debug, moderation, events, general, settings]
    except Exception as e:
        logger.error(f"Failed to import cog modules: {e}", exc_info=True)
        return

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


# ==========================================
# Main Entrypoint
# ==========================================
def main():
    """
    Main function to run the bot. Handles startup and fatal errors.
    """
    test_all_logging_levels()
    logger.info("Starting Discord Moderation Bot...")

    # Initialize AI model before bot startup
    try:
        logger.info("Initializing AI model before bot startup...")

        # Use asyncio to run the async initialization
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Try to initialize the AI model; this will set MODEL_STATE
        loop.run_until_complete(init_ai_model())


        if MODEL_STATE.init_error and not MODEL_STATE.available:
            logger.critical(f"AI model failed to initialize: {MODEL_STATE.init_error}")
            
    except Exception as e:
        logger.critical(f"Unexpected error during AI initialization: {e}", exc_info=True)
        

    # Bot Initialization
    discord_intents = discord.Intents.all()
    global discord_bot_instance
    discord_bot_instance = discord.Bot(intents=discord_intents)

    if not DISCORD_BOT_TOKEN:
        logger.critical(
            "'DISCORD_BOT_TOKEN' environment variable not set. "
            "Bot cannot start."
        )
        sys.exit(1)

    try:
        logger.info("Loading cogs...")
        load_cogs(discord_bot_instance)

        logger.info("Attempting to connect to Discord...")
        discord_bot_instance.run(DISCORD_BOT_TOKEN)
        # This line is only reached on a failed login or disconnect
        logger.critical(
            "Login failed or bot disconnected. "
            "Please check the token or connection."
        )
    except Exception as e:
        logger.critical(
            f"An unexpected error occurred while running the bot: {e}",
            exc_info=True
        )


if __name__ == "__main__":
    # Set the global exception hook to use the custom handler
    sys.excepthook = handle_exception
    main()
