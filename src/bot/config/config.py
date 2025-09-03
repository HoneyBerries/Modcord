"""
Configuration module for the Discord bot.

This module defines the `Config` class, which loads and provides access to
configuration settings from a YAML file.
"""

from pathlib import Path
import yaml

class Config:
    """
    Manages the bot's configuration, loaded from a YAML file.
    """
    def __init__(self, config_path: str):
        self._config_path = config_path
        self._config = self._load_config()

    def _load_config(self) -> dict:
        """
        Loads the YAML configuration file.
        """
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            # A more specific error message can be logged here
            raise
        except yaml.YAMLError:
            # A more specific error message can be logged here
            raise

    @property
    def server_rules(self) -> str:
        """
        Returns the server rules from the configuration.
        """
        return self._config.get("server_rules", "")

    @property
    def system_prompt(self) -> str:
        """
        Returns the system prompt from the configuration.
        """
        return self._config.get("system_prompt", "")

    @property
    def logging_config(self) -> dict:
        """
        Returns the logging configuration.
        """
        return self._config.get("logging", {})

# Create a default config instance
CONFIG_PATH = str(Path(__file__).resolve().parent.parent / "data/config.yml")
config = Config(CONFIG_PATH)
