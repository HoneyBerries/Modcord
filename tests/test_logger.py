import unittest
import logging
import os
import tempfile
import shutil
from pathlib import Path
from logger import get_logger, setup_logger, LOGS_DIR, _get_log_filename

class TestLoggerSystem(unittest.TestCase):
    def setUp(self):
        self.logger_name = "test_logger"
        self.logger = get_logger(self.logger_name)
        # Get the current timestamped log file
        self.log_file = _get_log_filename()

    def test_logger_creation(self):
        """Test that logger is created with correct name."""
        self.assertIsInstance(self.logger, logging.Logger)
        self.assertEqual(self.logger.name, self.logger_name)

    def test_console_and_file_handlers(self):
        """Test that logger has both console and file handlers."""
        handler_types = [type(h) for h in self.logger.handlers]
        self.assertIn(logging.StreamHandler, handler_types)
        self.assertIn(logging.FileHandler, handler_types)

    def test_log_file_written(self):
        """Test that log messages are written to the timestamped file."""
        test_message = "Test log message for file writing"
        self.logger.info(test_message)
        
        # Flush all handlers to ensure message is written
        for handler in self.logger.handlers:
            handler.flush()
        
        # Check that log file exists
        self.assertTrue(self.log_file.exists(), f"Log file {self.log_file} should exist")
        
        # Check that message is in the file
        with open(self.log_file, "r", encoding="utf-8") as f:
            contents = f.read()
        self.assertIn(test_message, contents)

    def test_log_format(self):
        """Test that log format matches expected pattern: [Date Time] [Level] [Module] Message"""
        test_message = "Test format message"
        self.logger.warning(test_message)  # Use warning so it shows in console too
        
        # Flush all handlers
        for handler in self.logger.handlers:
            handler.flush()
            
        # Read log file and check format
        with open(self.log_file, "r", encoding="utf-8") as f:
            contents = f.read()
        
        # Check that the format is correct: [YYYY-MM-DD HH:MM:SS] [WARNING] [test_logger] Test format message
        import re
        pattern = r'\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] \[WARNING\] \[test_logger\] Test format message'
        self.assertTrue(re.search(pattern, contents), f"Log format doesn't match expected pattern. Contents: {contents}")

    def test_timestamped_filename(self):
        """Test that log filename contains timestamp."""
        filename = self.log_file.name
        # Filename should match pattern: YYYY-MM-DD_HH-MM-SS.log
        import re
        pattern = r'\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.log'
        self.assertTrue(re.match(pattern, filename), f"Filename {filename} doesn't match expected timestamp pattern")

    def test_different_log_levels(self):
        """Test different log levels are handled correctly."""
        # Temporarily set logger to DEBUG level to capture debug messages
        original_level = self.logger.level
        self.logger.setLevel(logging.DEBUG)
        
        self.logger.debug("Debug message")
        self.logger.info("Info message") 
        self.logger.warning("Warning message")
        self.logger.error("Error message")
        self.logger.critical("Critical message")
        
        # Flush handlers
        for handler in self.logger.handlers:
            handler.flush()
            
        # Check that all messages are in the file (file handler logs everything DEBUG+)
        with open(self.log_file, "r", encoding="utf-8") as f:
            contents = f.read()
        
        self.assertIn("Debug message", contents)
        self.assertIn("Info message", contents)
        self.assertIn("Warning message", contents)
        self.assertIn("Error message", contents)
        self.assertIn("Critical message", contents)
        
        # Restore original level
        self.logger.setLevel(original_level)

    def tearDown(self):
        """Clean up: close handlers and remove log file."""
        # Close and remove all handlers to prevent file locking
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)
        
        # Clear the logger handlers cache
        logging.getLogger(self.logger_name).handlers.clear()
        
        # Clean up log file after each test
        if self.log_file.exists():
            try:
                self.log_file.unlink()
            except PermissionError:
                # If we can't delete it, it will be cleaned up later
                pass

if __name__ == "__main__":
    unittest.main()

if __name__ == "__main__":
    unittest.main()
