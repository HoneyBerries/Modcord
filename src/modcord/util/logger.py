import logging
from logging.handlers import RotatingFileHandler
import os
import sys
from pathlib import Path
from datetime import datetime
import warnings

# -------------------- Configuration --------------------
LOGS_DIR: Path = Path(__file__).resolve().parents[3] / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

LOG_FORMAT: str = "[%(asctime)s] [%(levelname)s] [%(name)s:%(funcName)s:%(lineno)d] %(message)s"
DATE_FORMAT: str = "%Y-%m-%d %H-%M-%S"

LOG_COLORS = {
    "DEBUG": "\033[36m",      # Cyan
    "INFO": "\033[32m",       # Green
    "WARNING": "\033[33m",    # Yellow
    "ERROR": "\033[31m",      # Red
    "CRITICAL": "\033[38;5;88m",  # Dark Red (ANSI 256-color)
}
RESET_COLOR = "\033[0m"

LOG_FILENAME: str = datetime.now().strftime(DATE_FORMAT) + ".log"
LOG_FILEPATH: Path = LOGS_DIR / LOG_FILENAME

# -------------------- Formatters --------------------
class ColorFormatter(logging.Formatter):
    """A custom formatter to add ANSI colors to console log messages."""

    def format(self, record: logging.LogRecord) -> str:
        color = LOG_COLORS.get(record.levelname, "")
        message = super().format(record)
        return f"{color}{message}{RESET_COLOR}" if color else message


plain_formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)


def should_use_color() -> bool:
    """Check if the console supports ANSI color codes."""
    try:
        return sys.stderr.isatty()
    except Exception:
        return False


color_formatter = ColorFormatter(LOG_FORMAT, datefmt=DATE_FORMAT) if should_use_color() else plain_formatter


# -------------------- Logger Setup --------------------

def setup_logger(logger_name: str) -> logging.Logger:
    """
    Configure and return a logger with a console and file handler.

    Args:
        logger_name (str): Name of the logger.
        logging_level (int | None): Optional logging level (defaults to MODCORD_LOG_LEVEL env or INFO).

    Returns:
        logging.Logger: Configured logger.
    """
    logger = logging.getLogger(logger_name)

    if logger.handlers:
        return logger

    base_level = logging.DEBUG
    logger.setLevel(base_level)
    logger.propagate = False

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(base_level)
    console_handler.setFormatter(color_formatter)
    logger.addHandler(console_handler)


    # File handler (DEBUG level)
    file_handler = RotatingFileHandler(
        LOG_FILEPATH,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(plain_formatter)
    logger.addHandler(file_handler)

    return logger


def get_logger(logger_name: str) -> logging.Logger:
    """Return a configured logger instance."""
    return setup_logger(logger_name)


# -------------------- Exception Handling --------------------
def handle_exception(exception_type, exception_instance, exception_traceback) -> None:
    """
    Log uncaught exceptions using the main logger.

    KeyboardInterrupt exceptions are passed to the default hook.
    """
    if issubclass(exception_type, KeyboardInterrupt):
        sys.__excepthook__(exception_type, exception_instance, exception_traceback)
    else:
        logging.error("Uncaught exception", exc_info=(exception_type, exception_instance, exception_traceback))


# -------------------- Suppress Noisy Libraries --------------------
for noisy_logger in [
    "vllm", "vllm.engine", "vllm.client", "transformers", "urllib3",
    "torch", "torch.distributed", "c10d", "gloo"
]:
    logging.getLogger(noisy_logger).setLevel(logging.ERROR)

os.environ.setdefault("GLOG_minloglevel", "2")   # 0=INFO,1=WARNING,2=ERROR
os.environ.setdefault("NCCL_DEBUG", "ERROR")

# Suppress repetitive user warnings from vllm
warnings.filterwarnings("ignore", category=UserWarning, module=r"vllm.*")


# Set global exception hook
sys.excepthook = handle_exception
