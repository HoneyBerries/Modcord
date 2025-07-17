import enum

class ActionType(enum.Enum):
    """
    Enum representing different types of actions that can be performed by the bot.
    """
    BAN = "ban"
    UNBAN = "unban"
    KICK = "kick"
    MUTE = "mute"
    WARN = "warn"
    DELETE = "delete"
    TIMEOUT = "timeout"
    NULL = "null"
    
    def __str__(self):
        return self.value