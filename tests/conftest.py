"""
Pytest configuration and fixtures for Modcord tests.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

# Mock heavy AI dependencies that aren't needed for unit tests
# These must be mocked before any imports from src/modcord
sys.modules['xgrammar'] = MagicMock()
sys.modules['xgrammar.grammar'] = MagicMock()

# Add src directory to path so imports work
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))
