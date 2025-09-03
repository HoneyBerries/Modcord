"""
Tests for the logger.
"""

import unittest
import logging
import os
from pathlib import Path
from unittest.mock import patch

from src.bot.config.logger import setup_logging, get_logger
from src.bot.config.config import config

class TestLogger(unittest.TestCase):
    """
    Tests for the logger.
    """

    def setUp(self):
        """
        Set up the test case.
        """
        self.log_file = Path(config.logging_config.get("log_file", "logs/bot.log"))
        if self.log_file.exists():
            self.log_file.unlink()

    @patch('src.bot.config.config.Config.logging_config', new_callable=unittest.mock.PropertyMock)
    def test_logger_setup(self, mock_logging_config):
        """
        Tests that the logger is set up correctly.
        """
        mock_logging_config.return_value = {
            "level": "DEBUG",
            "console_level": "INFO",
            "file_level": "DEBUG",
            "handlers": {
                "console": True,
                "file": True,
            },
            "log_file": str(self.log_file),
            "levels": {
                "test_module": "WARNING"
            }
        }
        
        setup_logging()

        # Test root logger
        root_logger = logging.getLogger()
        self.assertEqual(root_logger.level, logging.DEBUG)
        
        # Test module-specific logger
        module_logger = get_logger("test_module")
        self.assertEqual(module_logger.level, logging.WARNING)

        # Test log file creation
        self.assertTrue(self.log_file.exists())

        # Test logging to file
        test_message = "This is a test message."
        logger = get_logger("test_logger")
        logger.debug(test_message)

        with open(self.log_file, "r", encoding="utf-8") as f:
            log_content = f.read()
            self.assertIn(test_message, log_content)

    def tearDown(self):
        """
        Tear down the test case.
        """
        if self.log_file.exists():
            self.log_file.unlink()

        # Reset logging
        root = logging.getLogger()
        if root.handlers:
            for handler in root.handlers:
                root.removeHandler(handler)

if __name__ == "__main__":
    unittest.main()
