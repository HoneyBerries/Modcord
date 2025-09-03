"""
logging_utils.py

Centralized logging utilities for the Discord bot.

Features:
---------
1. Single log file per program run (timestamped name).
2. Unified log format: [YYYY-MM-DD HH:MM:SS] [LEVEL] [module] message
3. Colored console output (DEBUG=cyan, INFO=green, WARNING=yellow, ERROR=red, CRITICAL=magenta)
4. Thread-safe async queue for file logging
5. Public API: get_logger(), current_log_file(), reset_logging()
"""

from __future__ import annotations

import logging
import os
import sys
import queue
import ctypes
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple
from logging.handlers import QueueHandler, QueueListener

# ──────────────────────────────────────────────
# Module Globals
# ──────────────────────────────────────────────
LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

_log_filename: Optional[Path] = None
_file_handler: Optional[logging.FileHandler] = None
_console_handler: Optional[logging.Handler] = None
_queue_handler: Optional[QueueHandler] = None
_queue_listener: Optional[QueueListener] = None
_log_queue: Optional[queue.Queue] = None
_initialized_ansi = False

# ──────────────────────────────────────────────
# Formatter
# ──────────────────────────────────────────────
class ColoredFormatter(logging.Formatter):
    """Formatter that adds ANSI colors to console output."""

    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
    }
    RESET = '\033[0m'

    def format(self, record):
        message = super().format(record)
        if record.levelname in self.COLORS:
            color = self.COLORS[record.levelname]
            return message.replace(
                f'[{record.levelname}]',
                f'[{color}{record.levelname}{self.RESET}]'
            )
        return message

# ──────────────────────────────────────────────
# Private Helpers
# ──────────────────────────────────────────────
def _get_log_filename() -> Path:
    global _log_filename
    if _log_filename is None:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        _log_filename = LOGS_DIR / f"{timestamp}.log"
    return _log_filename

def _enable_windows_ansi() -> None:
    """Enable ANSI colors on Windows console."""
    global _initialized_ansi
    if _initialized_ansi or os.name != "nt":
        return
    _initialized_ansi = True

    try:
        import colorama  # type: ignore
        colorama.just_fix_windows_console()
        return
    except Exception:
        pass

    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)
    except Exception:
        pass

def _get_shared_handlers() -> Tuple[logging.FileHandler, logging.Handler]:
    """Return shared (file, console) handlers, creating if necessary."""
    global _file_handler, _console_handler

    log_format = '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'

    if _file_handler is None:
        _file_handler = logging.FileHandler(_get_log_filename(), encoding="utf-8")
        _file_handler.setLevel(logging.INFO)
        _file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))

    if _console_handler is None:
        _enable_windows_ansi()
        _console_handler = logging.StreamHandler()
        _console_handler.setLevel(logging.DEBUG)
        _console_handler.setFormatter(ColoredFormatter(log_format, datefmt=date_format))

    return _file_handler, _console_handler

# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────
def setup_logger(name: str) -> logging.Logger:
    """Configure and return a logger with file + console output."""
    global _queue_handler, _queue_listener, _log_queue

    logger = logging.getLogger(name or __name__)

    if _queue_handler is None:
        _log_queue = queue.Queue(-1)
        _queue_handler = QueueHandler(_log_queue)
        file_handler, _ = _get_shared_handlers()
        _queue_listener = QueueListener(_log_queue, file_handler)
        _queue_listener.start()

    for h in logger.handlers[:]:
        logger.removeHandler(h)

    logger.addHandler(_queue_handler)
    if _console_handler:
        logger.addHandler(_console_handler)

    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    return logger

def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return setup_logger(name)

def current_log_file() -> Optional[Path]:
    """Return current log file path, or None if not initialized."""
    return _log_filename

def reset_logging() -> None:
    """Reset all logging state (for tests or reconfiguration)."""
    global _file_handler, _console_handler, _queue_handler, _queue_listener
    global _log_filename, _log_queue, _initialized_ansi

    if _queue_listener:
        try:
            _queue_listener.stop()
        except Exception:
            pass
        _queue_listener = None

    for logger_name, logger in list(logging.Logger.manager.loggerDict.items()):
        if isinstance(logger, logging.Logger):
            for handler in logger.handlers[:]:
                try:
                    handler.close()
                except Exception:
                    pass
                logger.removeHandler(handler)

    root = logging.getLogger()
    for handler in root.handlers[:]:
        try:
            handler.close()
        except Exception:
            pass
        root.removeHandler(handler)

    _file_handler = None
    _console_handler = None
    _queue_handler = None
    _log_queue = None
    _log_filename = None
    _initialized_ansi = False

# ──────────────────────────────────────────────
# Suppress Noisy Third-Party Loggers
# ──────────────────────────────────────────────
logging.getLogger("discord").setLevel(logging.ERROR)
logging.getLogger("websockets").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)

# ──────────────────────────────────────────────
# Main guard (optional)
# ──────────────────────────────────────────────
if __name__ == "__main__":
    logger = get_logger("ModBot")

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception
    logger.info("Logger initialized successfully.")
