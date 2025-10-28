# Test Suite Documentation

This directory contains comprehensive unit tests for the Modcord project using pytest.

## Running Tests

### Run all tests
```bash
pytest tests/
```

### Run with coverage report
```bash
pytest tests/ --cov=src/modcord --cov-report=term-missing --cov-report=html
```

### Run specific test file
```bash
pytest tests/test_moderation_datatypes.py -v
```

### Run tests matching a pattern
```bash
pytest tests/ -k "test_action" -v
```

## Test Structure

### Test Files

- **test_moderation_datatypes.py** - Tests for core data structures (ActionType, ActionData, ModerationMessage, ModerationUser, ModerationChannelBatch, Command classes)
- **test_moderation_parsing.py** - Tests for JSON schema generation and AI response parsing
- **test_discord_utils.py** - Tests for Discord utility functions (formatting, permissions, message building)
- **test_discord_utils_async.py** - Async tests for Discord operations (message deletion, DM sending)
- **test_image_utils.py** - Tests for image processing utilities (hashing, downloading, resizing)
- **test_database.py** - Tests for database operations (initialization, logging, queries)
- **test_guild_settings.py** - Tests for guild settings management and persistence
- **test_logger.py** - Tests for logging configuration and setup

### Fixtures

Common test fixtures are defined in `conftest.py`:
- `mock_discord_message` - Mock Discord message object
- `mock_discord_member` - Mock Discord member object  
- `mock_discord_user` - Mock Discord user object
- `mock_discord_guild` - Mock Discord guild object
- `mock_pil_image` - Mock PIL image for testing
- `temp_database` - Temporary database for testing

## Coverage

The test suite achieves high coverage on testable utility and data modules:

- **moderation_parsing.py**: 85% coverage
- **image_utils.py**: 100% coverage
- **database.py**: 94% coverage
- **logger.py**: 90% coverage
- **guild_settings.py**: 74% coverage
- **moderation_datatypes.py**: 55% coverage (data structures)
- **discord_utils.py**: 38% coverage (utility functions)

**Note**: Many modules (bot commands, AI core, main.py, UI components) are integration/UI code that require complex Discord bot infrastructure. These are not included in unit tests as they would require extensive mocking and are better suited for integration testing.

## Dependencies

Tests require:
- pytest
- pytest-asyncio
- pytest-cov
- py-cord (Discord library)
- All project dependencies from requirements.txt

## Configuration

Test configuration is in `pytest.ini`:
- Test discovery patterns
- Coverage settings
- Async mode configuration
- Verbosity options
