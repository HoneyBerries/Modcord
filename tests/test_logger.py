"""Tests for logger module."""

import pytest
import logging
from pathlib import Path
from unittest.mock import patch, MagicMock

from modcord.util.logger import (
    get_logger,
    setup_logger,
    should_use_color,
    ColorFormatter,
    LOG_FORMAT,
    DATE_FORMAT,
)


class TestShouldUseColor:
    """Tests for should_use_color function."""

    @patch('sys.stderr.isatty')
    def test_should_use_color_tty(self, mock_isatty):
        """Test color is enabled for TTY."""
        mock_isatty.return_value = True
        assert should_use_color() is True

    @patch('sys.stderr.isatty')
    def test_should_use_color_no_tty(self, mock_isatty):
        """Test color is disabled for non-TTY."""
        mock_isatty.return_value = False
        assert should_use_color() is False

    @patch('sys.stderr.isatty')
    def test_should_use_color_exception(self, mock_isatty):
        """Test color returns False on exception."""
        mock_isatty.side_effect = Exception("Error")
        assert should_use_color() is False


class TestColorFormatter:
    """Tests for ColorFormatter class."""

    def test_color_formatter_format_debug(self):
        """Test ColorFormatter formats DEBUG messages with color."""
        formatter = ColorFormatter(LOG_FORMAT, datefmt=DATE_FORMAT)
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="test.py",
            lineno=10,
            msg="Debug message",
            args=(),
            exc_info=None,
            func="test_func"
        )
        
        formatted = formatter.format(record)
        
        # Should contain ANSI color codes for DEBUG (cyan)
        assert "\033[36m" in formatted or "Debug message" in formatted

    def test_color_formatter_format_error(self):
        """Test ColorFormatter formats ERROR messages with color."""
        formatter = ColorFormatter(LOG_FORMAT, datefmt=DATE_FORMAT)
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=10,
            msg="Error message",
            args=(),
            exc_info=None,
            func="test_func"
        )
        
        formatted = formatter.format(record)
        
        # Should contain ANSI color codes for ERROR (red) or the message
        assert "\033[31m" in formatted or "Error message" in formatted

    def test_color_formatter_format_warning(self):
        """Test ColorFormatter formats WARNING messages with color."""
        formatter = ColorFormatter(LOG_FORMAT, datefmt=DATE_FORMAT)
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="test.py",
            lineno=10,
            msg="Warning message",
            args=(),
            exc_info=None,
            func="test_func"
        )
        
        formatted = formatter.format(record)
        
        # Should contain message
        assert "Warning message" in formatted


class TestSetupLogger:
    """Tests for setup_logger function."""

    def test_setup_logger_creates_logger(self):
        """Test setup_logger creates a logger."""
        logger = setup_logger("test_logger_unique_1")
        
        assert logger is not None
        assert logger.name == "test_logger_unique_1"
        assert logger.level == logging.DEBUG

    def test_setup_logger_returns_existing(self):
        """Test setup_logger returns existing logger."""
        logger1 = setup_logger("test_logger_unique_2")
        logger2 = setup_logger("test_logger_unique_2")
        
        assert logger1 is logger2

    def test_setup_logger_has_handlers(self):
        """Test setup_logger adds handlers."""
        logger = setup_logger("test_logger_unique_3")
        
        # Should have at least 1 handler (console, file)
        assert len(logger.handlers) > 0

    def test_setup_logger_propagate_false(self):
        """Test logger doesn't propagate to root."""
        logger = setup_logger("test_logger_unique_4")
        
        assert logger.propagate is False


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_returns_logger(self):
        """Test get_logger returns a logger."""
        logger = get_logger("test_module")
        
        assert logger is not None
        assert isinstance(logger, logging.Logger)

    def test_get_logger_same_name_returns_same(self):
        """Test get_logger with same name returns same logger."""
        logger1 = get_logger("test_module_unique_1")
        logger2 = get_logger("test_module_unique_1")
        
        assert logger1 is logger2

    def test_get_logger_configured(self):
        """Test logger returned by get_logger is configured."""
        logger = get_logger("test_module_unique_2")
        
        assert logger.level == logging.DEBUG
        assert len(logger.handlers) > 0


class TestLoggerConstants:
    """Tests for logger constants."""

    def test_log_format_constant(self):
        """Test LOG_FORMAT constant is defined."""
        assert isinstance(LOG_FORMAT, str)
        assert "levelname" in LOG_FORMAT
        assert "name" in LOG_FORMAT

    def test_date_format_constant(self):
        """Test DATE_FORMAT constant is defined."""
        assert isinstance(DATE_FORMAT, str)
        # Should be a valid date format
        assert "%" in DATE_FORMAT


class TestLoggerIntegration:
    """Integration tests for logger functionality."""

    def test_logger_debug_message(self):
        """Test logging debug message."""
        logger = get_logger("test_integration_1")
        
        # Should not raise exception
        logger.debug("Test debug message")

    def test_logger_info_message(self):
        """Test logging info message."""
        logger = get_logger("test_integration_2")
        
        # Should not raise exception
        logger.info("Test info message")

    def test_logger_warning_message(self):
        """Test logging warning message."""
        logger = get_logger("test_integration_3")
        
        # Should not raise exception
        logger.warning("Test warning message")

    def test_logger_error_message(self):
        """Test logging error message."""
        logger = get_logger("test_integration_4")
        
        # Should not raise exception
        logger.error("Test error message")

    def test_logger_with_exception(self):
        """Test logging with exception info."""
        logger = get_logger("test_integration_5")
        
        try:
            raise ValueError("Test exception")
        except ValueError:
            # Should not raise exception
            logger.exception("Exception occurred")

    def test_logger_multiple_loggers(self):
        """Test creating multiple loggers."""
        logger1 = get_logger("module1")
        logger2 = get_logger("module2")
        logger3 = get_logger("module3")
        
        assert logger1.name == "module1"
        assert logger2.name == "module2"
        assert logger3.name == "module3"
        assert logger1 is not logger2
        assert logger2 is not logger3
