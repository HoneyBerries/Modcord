"""
AI moderation engine for Modcord.

This package implements the core AI inference pipeline:

- **ai_core.py**: Manages vLLM model lifecycle, handles synchronous inference
  wrapped in async wrappers, applies system prompt injection with server rules
  and channel guidelines, and performs batch generation with guided decoding

- **ai_moderation_processor.py**: High-level orchestration of the moderation
  pipeline - converts message batches into LLM conversations, builds dynamic
  JSON schemas and xgrammar constraints per channel, submits batches to vLLM,
  parses responses into moderation actions

Key Features:
- Thread-safe async/sync model initialization and cleanup
- Per-conversation constrained decoding with xgrammar to prevent hallucinations
- Dynamic schema generation to enforce valid user IDs and message lists
- Multimodal support (text + images) in message context
- Resource pooling and GPU memory management
"""