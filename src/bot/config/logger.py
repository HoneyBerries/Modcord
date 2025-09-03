"""
Logging configuration for the Discord bot.
"""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

from .config import config

class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors to console output based on log level."""

    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
    }
    RESET = '\033[0m'

    def format(self, record):
        log_format = f'[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s'
        formatter = logging.Formatter(log_format, '%Y-%m-%d %H:%M:%S')
        message = formatter.format(record)
        if record.levelname in self.COLORS:
            message = message.replace(f'[{record.levelname}]', f'[{self.COLORS[record.levelname]}{record.levelname}{self.RESET}]')
        return message

def setup_logging():
    """
    Configures the logging for the application.
    """
    log_config = config.logging_config
    log_level = log_config.get("level", "INFO").upper()

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Console Handler
    if log_config.get("handlers", {}).get("console", True):
        console_level = log_config.get("console_level", "INFO").upper()
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(console_level)
        console_handler.setFormatter(ColoredFormatter())
        root_logger.addHandler(console_handler)

    # File Handler
    if log_config.get("handlers", {}).get("file", True):
        log_file = log_config.get("log_file", "logs/bot.log")
        file_level = log_config.get("file_level", "DEBUG").upper()

        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(log_path, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
        file_handler.setLevel(file_level)
        file_formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s', '%Y-%m-%d %H:%M:%S')
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    # Set logging levels for specific modules
    for logger_name, level in log_config.get("levels", {}).items():
        logging.getLogger(logger_name).setLevel(level.upper())

    # Set third-party logging levels
    third_party_level = log_config.get("third_party_level", "WARNING").upper()
    logging.getLogger("discord").setLevel(third_party_level)
    logging.getLogger("websockets").setLevel(third_party_level)
    logging.getLogger("transformers").setLevel(third_party_level)

    # Exception hook
    sys.excepthook = handle_exception

def get_logger(name: str) -> logging.Logger:
    """
    Returns a logger with the specified name.
    """
    return logging.getLogger(name)

def handle_exception(exc_type, exc_value, exc_traceback):
    """
    Log uncaught exceptions.
    """
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger = get_logger("uncaught_exception")
    logger.critical("Uncaught exception:", exc_info=(exc_type, exc_value, exc_traceback))
