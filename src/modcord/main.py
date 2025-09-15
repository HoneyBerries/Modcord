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
from dotenv import load_dotenv

import discord

from .logger import get_logger, handle_exception
from .bot_config import bot_config

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
    """Load all bot cogs."""
    cog_module_names = [
        'modcord.cogs.general',
        'modcord.cogs.moderation',
        'modcord.cogs.debug',
        'modcord.cogs.events',
        'modcord.cogs.settings',
    ]
    for cog_module_name in cog_module_names:
        try:
            discord_bot_instance.load_extension(cog_module_name)
            logger.info(f"Loaded cog: {cog_module_name}")
        except Exception as e:
            logger.error(f"Failed to load cog {cog_module_name}: {e}", exc_info=True)


# ==========================================
# Main Entrypoint
# ==========================================
def main():
    """
    Main function to run the bot. Handles startup and fatal errors.
    """
    test_all_logging_levels()
    logger.info("Starting Discord Moderation Bot...")
    
    # Bot Initialization
    discord_intents = discord.Intents.all()
    global discord_bot_instance
    discord_bot_instance = discord.Bot(intents=discord_intents)

    if not DISCORD_BOT_TOKEN:
        logger.critical("'DISCORD_BOT_TOKEN' environment variable not set. Bot cannot start.")
        sys.exit(1)

    try:
        logger.info("Loading cogs...")
        load_cogs(discord_bot_instance)
        
        logger.info("Attempting to connect to Discord...")
        discord_bot_instance.run(DISCORD_BOT_TOKEN)
        # This line is only reached on a failed login or disconnect
        logger.critical("Login failed or bot disconnected. Please check the token or connection.")
    except Exception as e:
        logger.critical(f"An unexpected error occurred while running the bot: {e}", exc_info=True)


if __name__ == "__main__":
    # Set the global exception hook to use the custom handler
    sys.excepthook = handle_exception
    main()
