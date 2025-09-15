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

# Default path to the YAML configuration file (root-level data/config.yml)
CONFIG_PATH = str(Path(__file__).resolve().parent.parent.parent / "data/config.yml")


# Logger for this module
logger = get_logger("config_loader")


def load_config(config_file_path=None, path=None):
    """
    Load and parse the YAML configuration file.

    Args:
        config_file_path (str): Path to the YAML config file (default is "config.yml").
        path (str): Deprecated parameter name, use config_file_path instead.

    Returns:
        dict: Parsed configuration dictionary. Returns an empty dict on failure.
    """
    # Maintain backward compatibility with 'path' parameter
    if path is not None and config_file_path is None:
        config_file_path = path
    elif config_file_path is None:
        config_file_path = CONFIG_PATH
        
    try:
        with open(config_file_path, "r", encoding="utf-8") as file_handle:
            configuration_data = yaml.safe_load(file_handle)
            return configuration_data if configuration_data else {}
    except Exception as e:
        logger.error(f"[CONFIG] Failed to load config from {config_file_path}: {e}")
        return {}


def get_server_rules(configuration_data, guild_specific_rules=None, guild_rules=None):
    """
    Extract the server rules from the configuration or use dynamic guild rules.

    Args:
        configuration_data (dict): The configuration dictionary.
        guild_specific_rules (str, optional): Dynamic rules fetched from Discord channels.
                                     If provided, this takes precedence over config rules.
        guild_rules (str, optional): Deprecated parameter name, use guild_specific_rules instead.

    Returns:
        str: Server rules as a single formatted string.
             Returns guild_specific_rules if provided, otherwise falls back to config rules.
             Returns an empty string if no rules are found.
    """
    # Maintain backward compatibility with 'guild_rules' parameter
    if guild_rules is not None and guild_specific_rules is None:
        guild_specific_rules = guild_rules
        
    # Prioritize dynamic guild rules over config.yml rules
    if guild_specific_rules:
        return guild_specific_rules
    return configuration_data.get("server_rules", "")


def get_system_prompt(configuration_data, server_rules_content=None, server_rules=None):
    """
    Format and return the system prompt using server rules.

    The prompt should contain a `{SERVER_RULES}` placeholder which will be
    replaced with the actual rules string.

    Args:
        configuration_data (dict): The configuration dictionary.
        server_rules_content (str, optional): Server rules to be inserted into the prompt.
                                      If not provided, the placeholder will not be replaced.
        server_rules (str, optional): Deprecated parameter name, use server_rules_content instead.

    Returns:
        str: The formatted system prompt.
             If no prompt is defined in the config, returns an empty string.
    """
    # Maintain backward compatibility with 'server_rules' parameter
    if server_rules is not None and server_rules_content is None:
        server_rules_content = server_rules
        
    system_prompt_template = configuration_data.get("system_prompt", "")
    if server_rules_content is not None:
        return system_prompt_template.format(SERVER_RULES=server_rules_content)
    return system_prompt_template

