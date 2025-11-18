"""
Modcord - AI-Powered Discord Moderation Bot

Modcord is a sophisticated Discord moderation bot that leverages large language models
to automatically detect and respond to rule violations, while providing manual moderation
tools for server administrators.

Core Components:

- **AI Engine**: Integrates vLLM-based language models with guided decoding for
  accurate, constrained moderation decisions
- **Message Processing**: Batches messages from multiple channels for efficient
  bulk AI inference with per-channel context
- **Moderation Actions**: Supports automated warnings, message deletion, timeouts,
  kicks, and bans with automatic unban scheduling
- **Guild Settings**: Per-server configuration of AI enabled state, action toggles,
  and custom rules/guidelines
- **Interactive Console**: Live bot administration interface for status checks,
  guild inspection, and graceful restart/shutdown

Usage:
    from modcord.main import main
    main()  # Starts the bot with console interface
"""