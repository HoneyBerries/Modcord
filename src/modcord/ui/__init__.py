"""
User interface components for Modcord.

This package provides interactive interfaces for bot administration:

- **console.py**: Interactive developer console for live bot management. Features
  command-based interface with status checks, guild listing, log clearing, graceful
  shutdown/restart with process replacement. Uses prompt_toolkit for non-blocking
  I/O that doesn't interfere with Discord event handling.

- **guild_settings_ui.py**: Interactive Discord UI with button-based settings panel.
  Allows server admins to toggle AI enabled state and individual moderation action
  types via button callbacks. Includes permission checks and real-time embed updates.
"""
