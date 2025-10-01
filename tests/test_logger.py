import logging
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import modcord.util.logger as logger_module


class LoggerUtilitiesTests(unittest.TestCase):
    def test_color_formatter_wraps_with_ansi(self) -> None:
        formatter = logger_module.ColorFormatter("%(levelname)s:%(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=10,
            msg="boom",
            args=(),
            exc_info=None,
        )

        formatted = formatter.format(record)

        self.assertTrue(formatted.startswith(logger_module.LOG_COLORS["ERROR"]))
        self.assertTrue(formatted.endswith(logger_module.RESET_COLOR))
        self.assertIn("ERROR:boom", formatted)

    def test_should_use_color_swallows_exceptions(self) -> None:
        fake_stderr = MagicMock()
        fake_stderr.isatty.side_effect = RuntimeError("boom")
        with patch.object(logger_module.sys, "stderr", fake_stderr):
            self.assertFalse(logger_module.should_use_color())

    def test_setup_logger_installs_handlers_once(self) -> None:
        logger_name = "test_modcord_logger"
        with patch.object(logger_module, "color_formatter", logger_module.plain_formatter):
            log = logger_module.setup_logger(logger_name)

        try:
            self.assertEqual(len(log.handlers), 2)
            # Second call should not duplicate handlers
            log_again = logger_module.setup_logger(logger_name)
            self.assertIs(log, log_again)
            self.assertEqual(len(log_again.handlers), 2)
        finally:
            for handler in list(log.handlers):
                log.removeHandler(handler)
                handler.close()

        log_path = logger_module.LOG_FILEPATH
        if log_path.exists():
            # keep repo clean between runs
            try:
                os.remove(log_path)
            except OSError:
                pass


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
