"""
Discord message history fetching and conversion for moderation context.

This package provides:

- **discord_history_fetcher.py**: Fetches recent message history from Discord
  channels and converts them to ModerationMessage format. Handles adaptive paging
  to fetch exactly the needed number of messages, filters out bot messages,
  extracts embed content, downloads and resizes images for multimodal processing.

History is used to provide context to the AI model about recent channel activity
before the flagged messages, helping make better-informed moderation decisions.
"""