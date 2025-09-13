import enum
import sys

# Ensure this module object is reachable via several common import names so imports
# like `actions`, `src.actions`, `modcord.actions` and `src.modcord.actions` all
# refer to the same module object and the same ActionType class.
_this_module = sys.modules.get(__name__)
_aliases = [
    'actions',
    'src.actions',
    'modcord.actions',
    'src.modcord.actions',
]
for _alias in _aliases:
    if _alias not in sys.modules:
        sys.modules[_alias] = _this_module

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