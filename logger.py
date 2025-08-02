import logging
from pathlib import Path
from datetime import datetime

# Create logs directory
LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

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

    log_formatter = logging.Formatter(
        '[%(asctime)s %(levelname)s]: %(message)s',
        datefmt='%H:%M:%S'
    )

    # Create a new log file for each run, named with the current timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = LOGS_DIR / f"bot_{timestamp}.log"
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(log_formatter)

    # Console handler (still only warnings and above)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(log_formatter)

    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.propagate = False

    return logger

def get_logger(name: str) -> logging.Logger:
    return setup_logger(name)

# Create the main bot logger
main_logger = setup_logger("ModBot")

# Suppress noisy third-party loggers
logging.getLogger("transformers").setLevel(logging.ERROR)
