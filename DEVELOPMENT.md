# Modcord Development Workflow

## Package Structure

This project uses a `src/` layout with the `modcord` package located at `src/modcord/`. All imports should use absolute imports in the format `from modcord.module import something`.

## Recommended Development Workflow

### 1. Editable Installation (Recommended)

For development, install the package in editable mode:

```bash
pip install -e .
```

This allows you to:
- Import modcord modules from anywhere: `from modcord.logger import get_logger`
- Run the bot using: `python -m modcord`
- Run tests that use absolute imports
- Make changes to the code without reinstalling

### 2. Direct Module Execution (Alternative)

You can also run the bot directly:

```bash
python src/modcord/main.py
```

However, editable installation is preferred for development.

### 3. Console Script (After Installation)

Once installed, you can run:

```bash
modcord
```

## Import Guidelines

### ✅ Correct Import Patterns

```python
# Standard library imports first
import os
import sys
from pathlib import Path

# Third-party imports second
import discord
from discord.ext import commands

# Local imports last, using absolute imports
from modcord.logger import get_logger
from modcord.bot_settings import bot_settings
from modcord.cogs import general
```

### ❌ Avoid These Import Patterns

```python
# Don't use relative imports
from .logger import get_logger
from ..bot_settings import bot_settings

# Don't use src in imports
from src.modcord.logger import get_logger
```

## Running Tests

Run tests from the project root:

```bash
python -m unittest discover tests
```

Or run individual test files:

```bash
python tests/test_logger.py
```

## Code Style

The project follows PEP 8 guidelines:
- Maximum line length: 88 characters
- Use flake8 for linting: `flake8 src/ --max-line-length=88`
- Import order: standard library, third-party, local
- Two blank lines after class/function definitions at module level
- One blank line between methods

## Project Structure

```
Modcord/
├── src/
│   └── modcord/
│       ├── __init__.py
│       ├── __main__.py          # Enables `python -m modcord`
│       ├── main.py              # Main bot entry point
│       ├── logger.py            # Logging configuration
│       ├── bot_settings.py        # Bot configuration
│       ├── cogs/
│       │   ├── __init__.py
│       │   ├── general.py       # General commands
│       │   ├── moderation.py    # Moderation commands
│       │   └── ...
│       └── ...
├── tests/                       # Test files
├── setup.py                     # Package configuration
├── requirements.txt             # Dependencies
└── README.md
```