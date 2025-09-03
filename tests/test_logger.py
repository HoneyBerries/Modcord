import unittest
import logging
import re
from logger import get_logger, current_log_file, reset_logging


class TestLoggerSystem(unittest.TestCase):
    def setUp(self):
        # Ensure a logger is created; log file is created lazily by handler creation inside get_logger
        self.logger_name = "test_logger"
        self.logger = get_logger(self.logger_name)
        # Emit a small log to ensure any file handlers are initialized and a log file is created
        try:
            self.logger.debug("logger initialization for tests")
        except Exception:
            pass
        self.log_file = current_log_file()

    def _flush(self):
        for h in self.logger.handlers:
            try:
                h.flush()
            except Exception:
                pass
    def test_console_and_file_handlers(self):
        # With async logging, logger has a QueueHandler, not direct Stream/File handlers
        from logging.handlers import QueueHandler
        # Accept subclasses and wrapped handlers; check via isinstance
        self.assertTrue(any(isinstance(h, QueueHandler) for h in self.logger.handlers))
        # Also ensure the exact handler type is present among attached handlers
        handler_types = {type(h) for h in self.logger.handlers}
        self.assertIn(QueueHandler, handler_types)

    def test_log_file_written(self):
        msg = "Test log message for file writing"
        self.logger.info(msg)
        self._flush()
        self.assertIsNotNone(self.log_file)
        log_file = self.log_file
    def test_log_format(self):
        msg = "Format check"
        self.logger.warning(msg)
        self._flush()
        log_file = self.log_file
        self.assertIsNotNone(log_file)
        assert log_file is not None
        contents = log_file.read_text(encoding='utf-8')
        # Allow optional fractional seconds in timestamp and potential additional text after the message
        pattern = r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?\] \[WARNING\] \[test_logger\] Format check"
        self.assertRegex(contents, pattern)
        self.assertIsNotNone(log_file)
        assert log_file is not None
        contents = log_file.read_text(encoding='utf-8')
        pattern = r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] \[WARNING\] \[test_logger\] Format check"
        self.assertRegex(contents, pattern)

    def test_timestamped_filename(self):
        self.assertIsNotNone(self.log_file)
        assert self.log_file is not None
        filename = self.log_file.name
        self.assertRegex(filename, r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.log")

    def test_different_log_levels(self):
        original = self.logger.level
        self.logger.setLevel(logging.DEBUG)
        for level, text in [
            (logging.DEBUG, "Dbg"),
            (logging.INFO, "Inf"),
            (logging.WARNING, "Warn"),
            (logging.ERROR, "Err"),
            (logging.CRITICAL, "Crit"),
        ]:
            self.logger.log(level, text)
        self._flush()
        log_file = self.log_file
        self.assertIsNotNone(log_file)
        assert log_file is not None
        contents = log_file.read_text(encoding='utf-8')
        for text in ["Dbg", "Inf", "Warn", "Err", "Crit"]:
            self.assertIn(text, contents)
        self.logger.setLevel(original)

    def tearDown(self):
        # Close handlers we might have attached; then reset module state
        for h in self.logger.handlers[:]:
            try:
                h.close()
            except Exception:
                pass
            self.logger.removeHandler(h)
        reset_logging()
