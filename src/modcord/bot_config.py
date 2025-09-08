"""
Shared configuration and state management for the Discord Moderation Bot.
"""

import collections
from typing import Dict, DefaultDict
from collections import deque

from .logger import get_logger

logger = get_logger("bot_config")


class BotConfig:
    """
    Centralized configuration and state management for the bot.
    """
    
    def __init__(self):
        # Server rules cache - populated dynamically from Discord channels
        self.server_rules_cache: Dict[int, str] = {}  # guild_id -> rules_text
        
        # Per-channel chat history for AI context
        self.chat_history: DefaultDict[int, deque] = collections.defaultdict(
            lambda: collections.deque(maxlen=50)
        )
        
        logger.info("Bot configuration initialized")
    
    def get_server_rules(self, guild_id: int) -> str:
        """Get server rules for a guild."""
        return self.server_rules_cache.get(guild_id, "")
    
    def set_server_rules(self, guild_id: int, rules: str) -> None:
        """Set server rules for a guild."""
        self.server_rules_cache[guild_id] = rules
        logger.debug(f"Updated rules cache for guild {guild_id}")
    
    def add_message_to_history(self, channel_id: int, message_data: dict) -> None:
        """Add a message to the channel's chat history."""
        self.chat_history[channel_id].append(message_data)
    
    def get_chat_history(self, channel_id: int) -> list:
        """Get chat history for a channel."""
        return list(self.chat_history[channel_id])


# Global bot configuration instance
bot_config = BotConfig()