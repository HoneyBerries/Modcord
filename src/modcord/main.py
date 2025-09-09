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

from .logger import get_logger

# ==========================================
# Configuration and Logging Setup
# ==========================================

# Use pathlib for robust path management
# Set the base directory to the project root (up two levels from this file)
BASE_DIR = Path(__file__).resolve().parent.parent.parent
# Get logger for this module
logger = get_logger("main")

# Load environment variables from the .env file in the project root
load_dotenv(dotenv_path=BASE_DIR / ".env")
DISCORD_BOT_TOKEN = os.getenv('Mod_Bot_Token')

# ==========================================
# Bot Initialization
# ==========================================

intents = discord.Intents.all()
bot = discord.Bot(intents=intents)

# ==========================================
# Cog Loading
# ==========================================

def load_cogs():
    """Load all bot cogs."""
    cog_files = [
        'modcord.cogs.general',
        'modcord.cogs.moderation',
        'modcord.cogs.debug',
        'modcord.cogs.events'
    ]
    
    for cog in cog_files:
        try:
            bot.load_extension(cog)
            logger.info(f"Loaded cog: {cog}")
        except Exception as e:
            logger.error(f"Failed to load cog {cog}: {e}")


# ==========================================
# Main Entrypoint
# ==========================================

def main():
    """
    Main function to run the bot. Handles startup and fatal errors.
    """
    logger.info("Starting Discord Moderation Bot...")
    
    if not DISCORD_BOT_TOKEN:
        logger.critical("'Mod_Bot_Token' environment variable not set. Bot cannot start.")
        sys.exit(1)

    try:
        logger.info("Loading cogs...")
        load_cogs()
        
        logger.info("Attempting to connect to Discord...")
        bot.run(DISCORD_BOT_TOKEN)
    except discord.LoginFailure:
        logger.critical("Login failed. Please check if the bot token is correct.")
    except Exception as e:
        logger.critical(f"An unexpected error occurred while running the bot: {e}", exc_info=True)


if __name__ == "__main__":
    main()