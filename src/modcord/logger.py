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
formatter = logging.Formatter(log_format, datefmt=date_format)

# Generate a timestamped log filename (e.g. 2025-09-07_23-01-45.log)
LOG_FILENAME = datetime.now().strftime("%Y-%m-%d_%H-%M-%S.log")
LOG_FILEPATH = LOGS_DIR / LOG_FILENAME


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Set up a logger with file and console handlers.

    Args:
        name (str): The name of the logger.
        level (int): The logging level (default: logging.INFO).

    Returns:
        logging.Logger: Configured logger instance.

    Notes:
        - The logger is cached to prevent duplicate handlers.
        - Logs messages to both the console (warnings and above) and a rotating file (debug and above).
    """
    logger = logging.getLogger(name)

    # If the logger is already configured, just return it
    if logger.handlers:
        return logger

    logger.setLevel(level)
    logger.propagate = False

    # Console handler (warnings and above)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Rotating file handler (DEBUG and above)
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILEPATH, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance.

    Args:
        name (str): The name of the logger.

    Returns:
        logging.Logger: Logger instance.

    Notes:
        This is a convenience function that calls `setup_logger`.
    """
    return setup_logger(name)


# --- Uncaught Exception Handler ---
def handle_exception(exc_type, exc_value, exc_traceback):
    """
    Log uncaught exceptions using the root logger.

    Args:
        exc_type (type): The exception type.
        exc_value (Exception): The exception instance.
        exc_traceback (traceback): The traceback object.

    Notes:
        - KeyboardInterrupt exceptions are passed to the default exception handler.
        - Other exceptions are logged as errors using the root logger.
    """
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    main_logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))


# Main bot logger
main_logger = get_logger("main")

# Set the global exception hook to use the custom handler
sys.excepthook = handle_exception