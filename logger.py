"""
Enhanced logging system for Discord bot with color support and timestamped files.

This module provides a centralized logging setup that creates a single log file
per program run with timestamp-based naming and colored console output.

Features:
- Single timestamped log file per program run
- Colored console output for different log levels
- Format: [Date and Time] [Level] [Module] <Message>
- Centralized configuration across all modules
- Global exception hook to catch and log all uncaught exceptions

Example Usage:
--------------
```python
from logger import get_logger

logger = get_logger("my_module")
logger.info("This is an info message")
logger.warning("This is a warning")
logger.error("This is an error")
```
"""
import logging
from pathlib import Path
import sys
from datetime import datetime


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors to console output based on log level."""
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green  
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
    }
    RESET = '\033[0m'  # Reset color
    
    def format(self, record):
        # Get the original formatted message
        message = super().format(record)
        
        # Add color for console output
        if hasattr(record, 'levelname') and record.levelname in self.COLORS:
            color = self.COLORS[record.levelname]
            # Only color the level name part
            colored_message = message.replace(
                f'[{record.levelname}]', 
                f'[{color}{record.levelname}{self.RESET}]'
            )
            return colored_message
        return message


# Create logs directory
LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Create timestamped log file name (only created once per program run)
_log_filename = None
_file_handler = None
_console_handler = None

def _get_log_filename():
    """Get or create the timestamped log filename for this program run."""
    global _log_filename
    if _log_filename is None:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        _log_filename = LOGS_DIR / f"{timestamp}.log"
    return _log_filename

def _get_shared_handlers():
    """Get or create shared file and console handlers."""
    global _file_handler, _console_handler
    
    if _file_handler is None or _console_handler is None:
        # Log format: [Date and Time] [Level] [Module] <Message>
        log_format = '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s'
        date_format = '%Y-%m-%d %H:%M:%S'
        
        # File handler - logs everything to timestamped file
        file_formatter = logging.Formatter(log_format, datefmt=date_format)
        _file_handler = logging.FileHandler(_get_log_filename(), encoding='utf-8')
        _file_handler.setLevel(logging.DEBUG)
        _file_handler.setFormatter(file_formatter)
        
        # Console handler with colors - only warnings and above
        console_formatter = ColoredFormatter(log_format, datefmt=date_format)
        _console_handler = logging.StreamHandler()
        _console_handler.setLevel(logging.WARNING)
        _console_handler.setFormatter(console_formatter)
    
    return _file_handler, _console_handler

def setup_logger(name: str) -> logging.Logger:
    """
    Set up a logger with file and console handlers.
    
    Args:
        name: The name of the logger (typically the module name)
    
    Returns:
        logging.Logger: Configured logger instance
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
    """
    Get a logger instance. This is a convenience function.
    
    Args:
        name: The name of the logger (typically the module name)
        
    Returns:
        logging.Logger: Configured logger instance
    """
    return setup_logger(name)

# Suppress noisy third-party loggers
logging.getLogger("discord").setLevel(logging.ERROR)
logging.getLogger("websockets").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)

# Create the main bot logger
main_logger = setup_logger("ModBot")

# --- Uncaught Exception Handler ---
def handle_exception(exc_type, exc_value, exc_traceback):
    """
    Log uncaught exceptions using the main logger.
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
