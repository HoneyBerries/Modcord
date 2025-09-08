import unittest
from pathlib import Path
import time

class TestLogger(unittest.TestCase):
    def test_get_logger_and_file_write(self):
        from src.logger import get_logger, LOGS_DIR
        # Ensure logs directory exists
        self.assertTrue(Path(LOGS_DIR).exists())

        logger = get_logger("test_logger")
        # Record initial handlers count to ensure idempotent configuration
        initial_handlers = len(logger.handlers)

        # Log a unique message and flush file handlers
        unique_msg = f"unit-test-logger-unique-{time.time_ns()}"
        logger.info(unique_msg)

        # Force flush on any file handlers
        for h in logger.handlers:
            try:
                h.flush()
            except Exception:
                pass

        # Verify that rotating file exists and contains the logged message
        log_file = Path(LOGS_DIR) / ""
        self.assertTrue(log_file.exists(), "Log file bot.log should exist")
        content = log_file.read_text(encoding="utf-8")
        self.assertIn(unique_msg, content)

        # Calling get_logger again should not duplicate handlers
        logger2 = get_logger("test_logger")
        self.assertIs(logger, logger2)
        self.assertEqual(initial_handlers, len(logger2.handlers))

if __name__ == '__main__':
    unittest.main()
