import unittest
from pathlib import Path
import time

class TestLogger(unittest.TestCase):
    def test_get_logger_and_file_write(self):
        from modcord.logger import get_logger, LOGS_DIR
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

        # Verify that a log file was created and contains the message
        log_files = list(Path(LOGS_DIR).glob("*.log"))
        self.assertTrue(log_files, "No log files found in logs directory.")

        # Get the most recent log file
        latest_log_file = max(log_files, key=lambda p: p.stat().st_ctime)
        self.assertTrue(latest_log_file.exists(), "Log file should exist")

        content = latest_log_file.read_text(encoding="utf-8")
        self.assertIn(unique_msg, content)

        # Calling get_logger again should not duplicate handlers
        logger2 = get_logger("test_logger")
        self.assertIs(logger, logger2)
        self.assertEqual(initial_handlers, len(logger2.handlers))

if __name__ == '__main__':
    unittest.main()
