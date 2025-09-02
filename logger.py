"""
Robust, production-ready logging system for a Discord bot.

This module provides a centralized logging setup that is easily configurable
and can be used across multiple cogs.

Features:
- Centralized configuration.
- Rotating file logs to prevent large log files.
- Console logging for development.
- Optional structured (JSON) logging for production environments.
- Global exception hook to catch and log all uncaught exceptions.

Example Usage in a Cog:
------------------------
To use the logger in a cog, simply import the `get_logger` function
and get a logger instance for your cog. It's best practice to use
the `__name__` of the module as the logger name.

```python
# in your_cog.py
from discord.ext import commands
from .logger import get_logger

logger = get_logger(__name__)

class MyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        logger.info("MyCog has been loaded.")

    @commands.slash_command(name="my_command")
    async def my_command(self, ctx):
        logger.info(f"'{ctx.author}' used my_command.")
        await ctx.respond("Command executed!")

    @commands.Cog.listener()
    async def on_error(self, event):
        logger.error(f"An error occurred: {event}", exc_info=True)

```
"""
import logging
import logging.handlers
from pathlib import Path
import os
import sys
from pythonjsonlogger import jsonlogger

# Create logs directory
LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Check environment variable to determine log format
use_json_logs = os.getenv('LOG_JSON_FORMAT', 'false').lower() == 'true'

# Define log format
if use_json_logs:
    formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(name)s %(levelname)s %(funcName)s %(lineno)d %(message)s'
    )
else:
    log_format = '[%(asctime)s] [%(levelname)s] [%(name)s:%(funcName)s:%(lineno)d] %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    formatter = logging.Formatter(log_format, datefmt=date_format)


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Set up a logger with file and console handlers.
    Loggers are cached to prevent duplicate handlers.
    """
    logger = logging.getLogger(name)

    # If logger is already configured, just return it
    if logger.handlers:
        return logger

    logger.setLevel(level)
    logger.propagate = False

    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Create rotating file handler
    log_file = LOGS_DIR / "bot.log"
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=1024 * 1024, backupCount=5, encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance. This is a convenience function.
    """
    return setup_logger(name)

# Suppress noisy third-party loggers
logging.getLogger("discord").setLevel(logging.ERROR)
logging.getLogger("websockets").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)

# Create the main bot logger
main_logger = get_logger("ModBot")

# --- Uncaught Exception Handler ---
def handle_exception(exc_type, exc_value, exc_traceback):
    """
    Log uncaught exceptions using the root logger.
    Prevents the bot from crashing silently on unhandled exceptions.
    """
    if issubclass(exc_type, KeyboardInterrupt):
        # Let KeyboardInterrupt exit the program
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    # Log the exception with full traceback
    main_logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

# Set the global exception hook
sys.excepthook = handle_exception
