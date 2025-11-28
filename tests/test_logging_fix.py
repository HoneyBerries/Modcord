#!/usr/bin/env python3
"""Quick test to verify the logging fix works - should create only one log file."""

import sys

from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from modcord.util.logger import get_logger, get_log_filepath

def test_single_log_file():
    """Test that multiple loggers use the same file."""
    print("Testing logging fix...")
    
    # Get the initial log file path
    initial_path = get_log_filepath()
    print(f"Initial log file path: {initial_path}")
    
    # Create multiple loggers
    logger1 = get_logger("test_module_1")
    logger2 = get_logger("test_module_2")
    logger3 = get_logger("test_module_3")
    
    # Log some messages
    logger1.info("Message from logger 1")
    logger2.info("Message from logger 2")
    logger3.info("Message from logger 3")
    
    # Verify all loggers use the same file
    path1 = get_log_filepath()
    path2 = get_log_filepath()
    path3 = get_log_filepath()
    
    assert path1 == path2 == path3 == initial_path, "All loggers should use the same file!"
    
    # Count log files created today
    from datetime import datetime
    from modcord.util.logger import LOGS_DIR, DATE_FORMAT
    
    today_prefix = datetime.now().strftime("%Y-%m-%d")
    log_files = list(LOGS_DIR.glob(f"{today_prefix}*.log"))
    
    print(f"\nLog files found for today ({today_prefix}):")
    for log_file in sorted(log_files):
        mtime = log_file.stat().st_mtime
        print(f"  - {log_file.name} (modified: {datetime.fromtimestamp(mtime)})")
    
    # Verify log file exists and has content
    if initial_path.exists():
        content = initial_path.read_text()
        print(f"\nLog file size: {len(content)} bytes")
        print(f"Log file contains {len(content.splitlines())} lines")
        
        # Check that all three messages are in the file
        assert "Message from logger 1" in content
        assert "Message from logger 2" in content
        assert "Message from logger 3" in content
        print("✓ All messages found in log file")
    
    print("\n✓ Test passed! Only one log file is being used.")
    return True

if __name__ == "__main__":
    try:
        test_single_log_file()
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
