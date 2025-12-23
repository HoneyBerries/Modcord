"""
AI moderation engine for Modcord.

This package implements the AI-driven moderation pipeline using an OpenAI-compatible API:

- **ai_moderation_processor.py**: Orchestrates the moderation pipeline - converts
  message batches into chat completion requests, builds dynamic JSON schemas for
  structured outputs, submits concurrent requests using asyncio.gather(), and
  parses responses into moderation actions.

Key Features:
- Uses AsyncOpenAI client for inference (compatible with vLLM, LM Studio, Ollama, etc.)
- Per-conversation structured outputs with JSON schema enforcement
- Dynamic schema generation to enforce valid user IDs and message lists
- Multimodal support (text + images via URLs)
- Efficient concurrent request processing
"""