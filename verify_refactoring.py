#!/usr/bin/env python3
"""
Verification script to test the refactored bot structure.
This script tests if the bot can initialize properly without connecting to Discord.
"""

import asyncio
import sys
from unittest.mock import patch, MagicMock

def test_bot_initialization():
    """Test that the bot can initialize with all cogs."""
    print("Testing bot initialization...")
    
    try:
        # Mock Discord connection to avoid network calls
        with patch('discord.Bot.run') as mock_run:
            # Import and test the bot
            from bot import bot, load_cogs, main
            print("OK Bot module imported successfully")
            
            # Test cog loading
            asyncio.run(load_cogs())
            print("OK All cogs loaded successfully")
            
            # Test bot has correct attributes
            assert hasattr(bot, 'cogs')
            assert len(bot.cogs) >= 4  # We should have at least 4 cogs
            print(f"OK Bot has {len(bot.cogs)} cogs loaded")
            
            # List loaded cogs
            for cog_name in bot.cogs:
                print(f"  - {cog_name}")
            
            return True
            
    except Exception as e:
        print(f"FAIL Error during bot initialization: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_config_functionality():
    """Test the bot configuration system."""
    print("\nTesting bot configuration...")
    
    try:
        from bot_config import bot_config
        
        # Test server rules
        bot_config.set_server_rules(12345, "Test rules for guild")
        rules = bot_config.get_server_rules(12345)
        assert rules == "Test rules for guild"
        print("OK Server rules management working")
        
        # Test chat history
        bot_config.add_message_to_history(67890, {"role": "user", "content": "Hello world"})
        history = bot_config.get_chat_history(67890)
        assert len(history) == 1
        assert history[0]["content"] == "Hello world"
        print("OK Chat history management working")
        
        return True
        
    except Exception as e:
        print(f"FAIL Error testing bot config: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_individual_cogs():
    """Test that individual cogs can be instantiated."""
    print("\nTesting individual cogs...")
    
    mock_bot = MagicMock()
    mock_bot.latency = 0.05
    
    try:
        # Test Util Cog
        from cogs.util import UtilCog
        util_cog = UtilCog(mock_bot)
        print("OK UtilCog instantiated")

        # Test Moderation Cog
        from cogs.moderation import ModerationCog
        mod_cog = ModerationCog(mock_bot)
        print("OK ModerationCog instantiated")
        
        # Test Debug Cog
        from cogs.debug import DebugCog
        debug_cog = DebugCog(mock_bot)
        print("OK DebugCog instantiated")
        
        # Test Events Cog (without AI model loading)
        from cogs.events import EventsCog
        events_cog = EventsCog(mock_bot)
        print("OK EventsCog instantiated")
        
        return True
        
    except Exception as e:
        print(f"FAIL Error testing individual cogs: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all verification tests."""
    print("=" * 60)
    print("MODCORD BOT REFACTORING VERIFICATION")
    print("=" * 60)
    
    tests = [
        test_config_functionality,
        test_individual_cogs,
        test_bot_initialization,
    ]
    
    passed = 0
    for test in tests:
        if test():
            passed += 1
    
    print(f"\n{'-'*60}")
    print(f"RESULTS: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("SUCCESS All verification tests passed!")
        print("The refactored bot structure is working correctly.")
        return 0
    else:
        print("FAILURE Some tests failed.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
