import unittest
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
from logger import get_logger, setup_logger, LOGS_DIR

class TestLoggerSystem(unittest.TestCase):
    def setUp(self):
        self.logger_name = "test_logger"
        self.logger = get_logger(self.logger_name)
        self.log_file = LOGS_DIR / "bot.log"
        # Remove log file before each test for isolation
        if self.log_file.exists():
            self.log_file.unlink()

    def test_logger_creation(self):
        self.assertIsInstance(self.logger, logging.Logger)
        self.assertEqual(self.logger.name, self.logger_name)

    def test_console_and_file_handlers(self):
        handler_types = [type(h) for h in self.logger.handlers]
        self.assertIn(logging.StreamHandler, handler_types)
        self.assertIn(RotatingFileHandler, handler_types)

    def test_log_file_written(self):
        self.logger.info("Test log message")
        self.logger.handlers[1].flush()
        self.assertTrue(self.log_file.exists())
        with open(self.log_file, "r", encoding="utf-8") as f:
            contents = f.read()
        self.assertIn("Test log message", contents)

    def test_json_format_env(self):
        os.environ['LOG_JSON_FORMAT'] = 'true'
        logger_json = setup_logger("json_logger")
        logger_json.info("Json format test")
        logger_json.handlers[1].flush()
        with open(LOGS_DIR / "bot.log", "r", encoding="utf-8") as f:
            contents = f.read()
        self.assertIn('"message": "Json format test"', contents)
        del os.environ['LOG_JSON_FORMAT']

    def tearDown(self):
        # Clean up log file after each test
        if self.log_file.exists():
            self.log_file.unlink()

if __name__ == "__main__":
    unittest.main()
