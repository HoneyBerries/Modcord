"""
Run script for the Discord Moderation Bot
"""
import sys
import os
from pathlib import Path

# Add the src directory to Python path
project_root = Path(__file__).parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

# Run the main module
if __name__ == "__main__":
    from modcord.main import main
    main()
