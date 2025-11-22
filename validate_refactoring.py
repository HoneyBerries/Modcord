#!/usr/bin/env python3
"""
Validation script to check that the review system refactoring maintains correct imports and structure.
"""

import sys
import importlib.util

def check_module(module_path: str, module_name: str) -> bool:
    """Check if a module can be imported successfully."""
    try:
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            print(f"❌ Failed to load spec for {module_name}")
            return False
        
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        print(f"✅ Successfully imported {module_name}")
        return True
    except Exception as e:
        print(f"❌ Failed to import {module_name}: {e}")
        return False

def check_function_exists(module, function_name: str) -> bool:
    """Check if a function exists in a module."""
    if hasattr(module, function_name):
        print(f"  ✅ Function '{function_name}' exists")
        return True
    else:
        print(f"  ❌ Function '{function_name}' not found")
        return False

def main():
    print("=" * 60)
    print("Validating Review System Refactoring")
    print("=" * 60)
    
    all_passed = True
    
    # Check review_notifications module
    print("\n📦 Checking review_notifications.py...")
    try:
        from src.modcord.moderation.review_notifications import ReviewNotificationManager
        print("✅ ReviewNotificationManager imported")
        
        # Check for new static methods
        if hasattr(ReviewNotificationManager, 'validate_review_channels'):
            print("  ✅ validate_review_channels() exists")
        else:
            print("  ❌ validate_review_channels() not found")
            all_passed = False
            
        if hasattr(ReviewNotificationManager, 'build_role_mentions'):
            print("  ✅ build_role_mentions() exists")
        else:
            print("  ❌ build_role_mentions() not found")
            all_passed = False
            
    except Exception as e:
        print(f"❌ Failed to import review_notifications: {e}")
        all_passed = False
    
    # Check review_ui module
    print("\n📦 Checking review_ui.py...")
    try:
        from src.modcord.bot.review_ui import check_moderator_permission
        print("✅ check_moderator_permission() imported")
    except Exception as e:
        print(f"❌ Failed to import review_ui: {e}")
        all_passed = False
    
    # Check moderation_helper module
    print("\n📦 Checking moderation_helper.py...")
    try:
        from src.modcord.moderation.moderation_helper import find_target_user_in_batch, find_pivot_message
        print("✅ find_target_user_in_batch() imported")
        print("✅ find_pivot_message() imported")
    except Exception as e:
        print(f"❌ Failed to import moderation_helper: {e}")
        all_passed = False
    
    # Check debug_cmds module
    print("\n📦 Checking debug_cmds.py...")
    try:
        from src.modcord.bot.debug_cmds import DebugCog
        print("✅ DebugCog imported")
    except Exception as e:
        print(f"❌ Failed to import debug_cmds: {e}")
        all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ All validation checks passed!")
        return 0
    else:
        print("❌ Some validation checks failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
