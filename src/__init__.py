# Explicit package for application modules.

# Create aliases so various import paths point to the same module objects
# This prevents duplicate definitions (e.g., multiple ActionType enums) when
# tests or code import modules via different names (src.actions, actions, modcord.actions).
import importlib
import sys

_alias_names = [
    "actions",
    "ai_model",
    "bot_helper",
    "bot_config",
    "config_loader",
    "logger",
    "main",
]
for _n in _alias_names:
    target = f"src.modcord.{_n}"
    try:
        mod = importlib.import_module(target)
        # Map both 'src.<name>' and the top-level '<name>' to the same module object
        sys.modules[f"src.{_n}"] = mod
        sys.modules[_n] = mod
        globals()[_n] = mod
    except Exception:
        # It's fine if some modules aren't present in all environments/tests
        continue

