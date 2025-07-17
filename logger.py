"""
Centralized Logging Configuration
================================

This module provides a centralized logging setup for the Discord Moderation Bot.
Creates structured logs in the /logs/ directory with rotation and different log levels.
"""

import logging
import logging.handlers
from pathlib import Path

# Create logs directory
LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

def setup_logger(name: str) -> logging.Logger:
    """
    Set up a logger with file and console handlers.
    
    Args:
        name (str): Name of the logger. If None, uses the root logger.
        
    Returns:
        logging.Logger: Configured logger instance.
    """
    logger_name = name or __name__
    logger = logging.getLogger(logger_name)
    
    # Prevent duplicate handlers if logger already exists
    if logger.handlers:
        return logger
    
    logger.setLevel(logging.DEBUG)  # All logs (including debug) go to handlers
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    simple_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # File handler for all logs (with daily rotation and timestamped filenames)
    all_logs_file = LOGS_DIR / "bot.log"
    file_handler = logging.handlers.TimedRotatingFileHandler(
        all_logs_file,
        when="midnight",           # Rotate at midnight
        interval=1,                # Every day
        backupCount=14,            # Keep 14 days of logs
        encoding='utf-8',
        utc=True                   # Use UTC timestamps
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)

    # File handler for errors only (also timestamped)
    error_logs_file = LOGS_DIR / "errors.log"
    error_handler = logging.handlers.TimedRotatingFileHandler(
        error_logs_file,
        when="midnight",
        interval=1,
        backupCount=14,
        encoding='utf-8',
        utc=True
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(detailed_formatter)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)  # Only warnings and above to console
    console_handler.setFormatter(simple_formatter)
    
    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(error_handler)
    logger.addHandler(console_handler)
    logger.propagate = False  # <-- Prevent messages from going to the root logger
    
    return logger

def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance. Creates one if it doesn't exist.
    
    Args:
        name (str): Name of the logger module.
        
    Returns:
        logging.Logger: Logger instance.
    """
    return setup_logger(name)

# Create the main bot logger
main_logger = setup_logger("ModBot")

# Suppress noisy third-party loggers
logging.getLogger("discord").setLevel(logging.WARNING)
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.WARNING)