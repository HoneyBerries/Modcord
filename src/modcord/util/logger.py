import logging
from logging.handlers import RotatingFileHandler
import os
import sys
from pathlib import Path
from datetime import datetime
import warnings
from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import ANSI

# -------------------- Configuration --------------------
LOGS_DIR: Path = (Path(__file__).parents[3] / "logs").resolve()
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
    """Formatter that applies ANSI color codes to log records during console output."""

    def format(self, record: logging.LogRecord) -> str:
        color = LOG_COLORS.get(record.levelname, "")
        message = super().format(record)
        return f"{color}{message}{RESET_COLOR}" if color else message


class PromptToolkitHandler(logging.Handler):
    """Custom logging handler that uses prompt_toolkit's print to avoid interfering with prompts."""

    def __init__(self, formatter: logging.Formatter | None = None):
        super().__init__()
        if formatter:
            self.setFormatter(formatter)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            print_formatted_text(ANSI(msg))
        except Exception:
            self.handleError(record)


plain_formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)


def should_use_color() -> bool:
    """Return ``True`` when the current environment supports colorized output."""
    try:
        return sys.stderr.isatty()
    except Exception:
        return False


color_formatter = ColorFormatter(LOG_FORMAT, datefmt=DATE_FORMAT) if should_use_color() else plain_formatter


# -------------------- Logger Setup --------------------

def setup_logger(logger_name: str) -> logging.Logger:
    """Configure and return a logger with console and rotating file handlers.

    Parameters
    ----------
    logger_name:
        Name of the logger to configure.

    Returns
    -------
    logging.Logger
        Configured logger instance.
    """
    logger = logging.getLogger(logger_name)

    if logger.handlers:
        return logger

    base_level = logging.DEBUG
    logger.setLevel(base_level)
    logger.propagate = False

    # Console handler using prompt_toolkit integration
    console_handler = PromptToolkitHandler(formatter=color_formatter)
    console_handler.setLevel(base_level)
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
    """Retrieve a logger configured for Modcord, creating it if necessary.

    Parameters
    ----------
    logger_name:
        Name of the logger requested by the caller.

    Returns
    -------
    logging.Logger
        Logger instance ready for use.
    """
    return setup_logger(logger_name)


# -------------------- Exception Handling --------------------
def handle_exception(exception_type, exception_instance, exception_traceback) -> None:
    """Log uncaught exceptions using the centralized logging configuration.

    Parameters
    ----------
    exception_type:
        Exception class that was raised.
    exception_instance:
        Exception instance produced by the runtime.
    exception_traceback:
        Traceback object associated with the exception.
    """
    if issubclass(exception_type, KeyboardInterrupt):
        sys.__excepthook__(exception_type, exception_instance, exception_traceback)
    else:
        logging.error("Uncaught exception", exc_info=(exception_type, exception_instance, exception_traceback))


# -------------------- Suppress Noisy Libraries --------------------
NOISY_LOGGERS = [
    "vllm", "vllm.engine", "vllm.client", "transformers", "urllib3",
    "torch", "torch.distributed", "c10d", "gloo",
    # Silence Discord internals and networking layers that spam INFO messages
    "discord", "discord.gateway", "discord.client", "discord.http",
    "websockets", "aiohttp", "cuda"
]

for noisy_logger in NOISY_LOGGERS:
    lg = logging.getLogger(noisy_logger)
    lg.setLevel(logging.ERROR)
    lg.propagate = False
    # Clear any handlers libraries may have added so output does not bypass our handler
    lg.handlers = []

os.environ.setdefault("GLOG_minloglevel", "2")   # 0=INFO,1=WARNING,2=ERROR
os.environ.setdefault("NCCL_DEBUG", "ERROR")

# Suppress repetitive user warnings from vllm
warnings.filterwarnings("ignore", category=UserWarning, module=r"vllm.*")


# Set global exception hook
sys.excepthook = handle_exception