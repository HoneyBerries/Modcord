"""
Module defining an enumeration for various moderation actions.
"""

from enum import Enum

class ActionType(Enum):
    """
    Enum representing different types of moderation actions.
    """

    BAN = "ban"
    UNBAN = "unban"
    KICK = "kick"
    WARN = "warn"
    DELETE = "delete"
    TIMEOUT = "timeout"
    NULL = "null"
    
    def __str__(self):
        return self.value