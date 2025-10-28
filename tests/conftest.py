"""
Pytest configuration and fixtures for Modcord tests.
"""

import sys
from pathlib import Path

# Add src directory to path so imports work
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))
