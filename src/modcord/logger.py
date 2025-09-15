import logging
import logging.handlers
import sys
from datetime import datetime
from pathlib import Path

# Create a logs directory at the project root
LOGS_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)


# Define the log format and date format for log messages
log_format = '[%(asctime)s] [%(levelname)s] [%(name)s:%(funcName)s:%(lineno)d] %(message)s'
date_format = '%Y-%m-%d %H:%M:%S'

# ANSI color codes for log levels
LOG_COLORS = {
    'DEBUG': '\033[36m',     # Cyan
    'INFO': '\033[32m',     # Green
    'WARNING': '\033[33m',  # Yellow
    'ERROR': '\033[31m',     # Red
    'CRITICAL': '\033[38;5;88m', # Dark Red (ANSI 256-color)
}
RESET_COLOR = '\033[0m'

class ColorFormatter(logging.Formatter):
    """A custom formatter to add color to log messages."""
    def format(self, record):
        color = LOG_COLORS.get(record.levelname, '')
        message = super().format(record)
        if color:
            message = f"{color}{message}{RESET_COLOR}"
        return message

plain_formatter = logging.Formatter(log_format, datefmt=date_format)
color_formatter = ColorFormatter(log_format, datefmt=date_format)

# Use a stable log filename so the project writes to a single file regardless
# of import path (helps tests that look for the most-recent log file).
LOG_FILENAME = "modcord.log"
LOG_FILEPATH = LOGS_DIR / LOG_FILENAME


def setup_logger(logger_name: str, logging_level: int = logging.DEBUG) -> logging.Logger:
    """
    Set up a logger with file and console handlers.

    Args:
        logger_name (str): The name of the logger.
        logging_level (int): The logging level (default: logging.DEBUG).

    Returns:
        logging.Logger: Configured logger instance.

    Notes:
        - The logger is cached to prevent duplicate handlers.
        - Logs messages to both the console (warnings and above) and a rotating file (debug and above).
    """
    logger = logging.getLogger(logger_name)

    # If the logger is already configured, just return it
    if logger.handlers:
        return logger

    logger.setLevel(logging_level)
    logger.propagate = False


    # Console handler (DEBUG and above, colored)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(color_formatter)
    logger.addHandler(console_handler)

    # Rotating file handler (DEBUG and above, plain)
    # Rotating file handler to avoid unbounded file growth. Keep it readable
    # by tests by writing to a consistent filepath.
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILEPATH, encoding="utf-8", maxBytes=5 * 1024 * 1024, backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(plain_formatter)
    logger.addHandler(file_handler)

    return logger


def get_logger(logger_name: str) -> logging.Logger:
    """
    Get a logger instance.

    Args:
        logger_name (str): The name of the logger.

    Returns:
        logging.Logger: Logger instance.
    """
    return setup_logger(logger_name)


# --- Uncaught Exception Handler ---
def handle_exception(exception_type, exception_instance, exception_traceback):
    """
    Log uncaught exceptions using the root logger.

    Args:
        exception_type (type): The exception type.
        exception_instance (Exception): The exception instance.
        exception_traceback (traceback): The traceback object.

    Notes:
        - KeyboardInterrupt exceptions are passed to the default exception handler.
        - Other exceptions are logged as errors using the root logger.
    """
    if issubclass(exception_type, KeyboardInterrupt):
        sys.__excepthook__(exception_type, exception_instance, exception_traceback)
        return
    main_logger.error("Uncaught exception", exc_info=(exception_type, exception_instance, exception_traceback))

# Main bot logger
main_logger = get_logger("main")

# Set the global exception hook to use the custom handler
sys.excepthook = handle_exception
