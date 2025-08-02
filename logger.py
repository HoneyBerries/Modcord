import logging
from pathlib import Path
from datetime import datetime

# Create logs directory
LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Global shared handlers - created once and reused
_shared_file_handler = None
_shared_console_handler = None

def _get_shared_handlers():
    """Get or create shared file and console handlers."""
    global _shared_file_handler, _shared_console_handler
    
    if _shared_file_handler is None:
        log_formatter = logging.Formatter(
            '[%(asctime)s %(levelname)s] [%(name)s]: %(message)s',
            datefmt='%H:%M:%S'
        )

        # Create a single log file for the entire application
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_file = LOGS_DIR / f"{timestamp}.log"
        _shared_file_handler = logging.FileHandler(log_file, encoding='utf-8')
        _shared_file_handler.setLevel(logging.DEBUG)
        _shared_file_handler.setFormatter(log_formatter)

        # Console handler
        _shared_console_handler = logging.StreamHandler()
        _shared_console_handler.setLevel(logging.WARNING)
        _shared_console_handler.setFormatter(log_formatter)

    return _shared_file_handler, _shared_console_handler

def setup_logger(name: str) -> logging.Logger:
    """
    Set up a logger with file and console handlers.
    """
    logger_name = name or __name__
    logger = logging.getLogger(logger_name)

    # Prevent duplicate handlers if logger already exists
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    # Get shared handlers
    file_handler, console_handler = _get_shared_handlers()

    # Add handlers to logger
    if file_handler is not None:
        logger.addHandler(file_handler)
    if console_handler is not None:
        logger.addHandler(console_handler)
    logger.propagate = False

    return logger

def get_logger(name: str) -> logging.Logger:
    return setup_logger(name)

# Create the main bot logger
main_logger = setup_logger("ModBot")

# Suppress noisy third-party loggers
logging.getLogger("transformers").setLevel(logging.ERROR)
