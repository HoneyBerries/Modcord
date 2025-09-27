import logging
import os
import sys
from pathlib import Path
from datetime import datetime
import warnings

# Create a logs directory at the project root
LOGS_DIR = Path(__file__).resolve().parents[3] / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)


# Define the log format and date format for log messages
log_format = '[%(asctime)s] [%(levelname)s] [%(name)s:%(funcName)s:%(lineno)d] %(message)s'
date_format = '%Y-%m-%d %H-%M-%S'

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

def should_use_color() -> bool:
    try:
        return sys.stderr.isatty()
    except Exception:
        return False

color_formatter = ColorFormatter(log_format, datefmt=date_format) if should_use_color() else plain_formatter


# Log filename with timestamp
LOG_FILENAME = datetime.now().strftime(date_format) + ".log"
LOG_FILEPATH = LOGS_DIR / LOG_FILENAME


def resolve_log_level(default_level: int = logging.INFO) -> int:
    level_name = os.environ.get("MODCORD_LOG_LEVEL", "").upper().strip()
    if level_name:
        return getattr(logging, level_name, default_level)
    return default_level


def setup_logger(logger_name: str, logging_level: int | None = None) -> logging.Logger:
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

    base_level = logging_level if logging_level is not None else resolve_log_level()
    logger.setLevel(base_level)
    logger.propagate = False


    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(base_level)
    console_handler.setFormatter(color_formatter)
    logger.addHandler(console_handler)

    # Rotating file handler (DEBUG and above, plain)
    from logging.handlers import RotatingFileHandler

    file_handler = RotatingFileHandler(
        LOG_FILEPATH,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
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

# Reduce vllm and related noisy loggers to WARNING to avoid INFO/DEBUG spam.
logging.getLogger("vllm").setLevel(logging.ERROR)
logging.getLogger("vllm.engine").setLevel(logging.ERROR)
logging.getLogger("vllm.client").setLevel(logging.ERROR)
# Optionally reduce other noisy libs commonly used with vllm:
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)

# Lower Python-level loggers for noisy libs
os.environ.setdefault("TORCH_CPP_LOG_LEVEL", "ERROR")
os.environ.setdefault("GLOG_minloglevel", "2")   # 0=INFO,1=WARNING,2=ERROR
os.environ.setdefault("NCCL_DEBUG", "ERROR")

logging.getLogger("torch").setLevel(logging.ERROR)
logging.getLogger("torch.distributed").setLevel(logging.ERROR)
logging.getLogger("c10d").setLevel(logging.ERROR)
logging.getLogger("gloo").setLevel(logging.ERROR)

# Optionally suppress repetitive UserWarnings from vllm modules
warnings.filterwarnings("ignore", category=UserWarning, module=r"vllm.*")

# Main bot logger
main_logger = get_logger("main")

# Set the global exception hook to use the custom handler
sys.excepthook = handle_exception
