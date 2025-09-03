"""
Main entry point for the Discord bot.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bot.core.bot import Bot
from bot.config.logger import setup_logging, get_logger

def main():
    """
    Main function to run the bot.
    """
    # Load environment variables
    load_dotenv()
    DISCORD_BOT_TOKEN = os.getenv('Mod_Bot_Token')

    # Set up logging
    setup_logging()
    logger = get_logger(__name__)

    if not DISCORD_BOT_TOKEN:
        logger.critical("'Mod_Bot_Token' environment variable not set. Bot cannot start.")
        sys.exit(1)

    try:
        logger.info("Starting Discord Moderation Bot...")
        bot = Bot()
        bot.run(DISCORD_BOT_TOKEN)
    except Exception as e:
        logger.critical(f"An unexpected error occurred while running the bot: {e}", exc_info=True)

if __name__ == "__main__":
    main()
