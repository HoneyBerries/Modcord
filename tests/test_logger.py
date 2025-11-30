import logging
import pytest
from modcord.util.logger import get_logger, setup_logger, ColorFormatter, PromptToolkitHandler, get_log_filepath, should_use_color, handle_exception

class DummyStream:
    def __init__(self):
        self.written = []
    def write(self, msg):
        self.written.append(msg)
    def isatty(self):
        return True


def test_get_logger_returns_logger():
    logger = get_logger("test_logger")
    assert isinstance(logger, logging.Logger)
    assert any(isinstance(h, logging.Handler) for h in logger.handlers)


def test_setup_logger_idempotent():
    logger1 = setup_logger("test_logger_idem")
    logger2 = setup_logger("test_logger_idem")
    assert logger1 is logger2
    assert len(logger1.handlers) > 0


def test_color_formatter_applies_color():
    formatter = ColorFormatter("%(levelname)s %(message)s")
    record = logging.LogRecord("test", logging.ERROR, "", 0, "error occurred", None, None)
    formatted = formatter.format(record)
    assert "\033[31m" in formatted and "error occurred" in formatted


def test_should_use_color_true(monkeypatch):
    monkeypatch.setattr("sys.stderr", DummyStream())
    assert should_use_color() is True


def test_get_log_filepath_creates_path():
    path = get_log_filepath()
    assert path.exists() or path.parent.exists()


def test_handle_exception_logs_error(caplog):
    class DummyException(Exception):
        pass
    with caplog.at_level(logging.ERROR):
        try:
            raise DummyException("fail")
        except DummyException as exc:
            handle_exception(DummyException, exc, exc.__traceback__)
    assert any("Uncaught exception" in r.message for r in caplog.records)
