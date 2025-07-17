"""
config_loader.py
----------------
Utility module for loading and accessing configuration values from a YAML file
(commonly `config.yml`). Provides functions to extract server rules, construct
system prompts, and access the full config structure.

Functions:
    load_config(path): Load and parse the YAML configuration file.
    get_server_rules(config): Extract server rules from the config dictionary.
    get_system_prompt(config, server_rules): Format and return the system prompt using server rules.
"""

from pathlib import Path
import yaml
from logger import get_logger

# Default path to the YAML configuration file
CONFIG_PATH = str(Path(__file__).parent / "config.yml")


# Logger for this module
logger = get_logger("config_loader")


def load_config(path=CONFIG_PATH):
    """
    Load and parse the YAML configuration file.

    Args:
        path (str): Path to the YAML config file (default is "config.yml").

    Returns:
        dict: Parsed configuration dictionary. Returns an empty dict on failure.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            return config if config else {}
    except Exception as e:
        logger.error(f"[CONFIG] Failed to load config from {path}: {e}")
        return {}


def get_server_rules(config, guild_rules=None):
    """
    Extract the server rules from the configuration or use dynamic guild rules.

    Args:
        config (dict): The configuration dictionary.
        guild_rules (str, optional): Dynamic rules fetched from Discord channels.
                                     If provided, this takes precedence over config rules.

    Returns:
        str: Server rules as a single formatted string.
             Returns guild_rules if provided, otherwise falls back to config rules.
             Returns an empty string if no rules are found.
    """
    # Prioritize dynamic guild rules over config.yml rules
    if guild_rules:
        return guild_rules
    return config.get("server_rules", "")


def get_system_prompt(config, server_rules=None):
    """
    Format and return the system prompt using server rules.

    The prompt should contain a `{SERVER_RULES}` placeholder which will be
    replaced with the actual rules string.

    Args:
        config (dict): The configuration dictionary.
        server_rules (str, optional): Server rules to be inserted into the prompt.
                                      If not provided, the placeholder will not be replaced.

    Returns:
        str: The formatted system prompt.
             If no prompt is defined in the config, returns an empty string.
    """
    prompt = config.get("system_prompt", "")
    if server_rules is not None:
        return prompt.format(SERVER_RULES=server_rules)
    return prompt

