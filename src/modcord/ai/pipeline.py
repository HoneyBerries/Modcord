"""High-level helpers for managing the AI moderation pipeline lifecycle."""
from __future__ import annotations

from typing import Optional, Tuple

from modcord.ai.ai_moderation_processor import moderation_processor, model_state
from modcord.util.logger import get_logger

logger = get_logger("ai_pipeline")


async def initialize_pipeline(model: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """Initialize the moderation pipeline.

    Args:
        model: Optional override for the model identifier.

    Returns:
        Tuple of (available flag, init error message).
    """

    logger.info("[AI PIPELINE] Initializing moderation pipeline…")
    await moderation_processor.init_model(model)
    await moderation_processor.start_batch_worker()
    return model_state.available, model_state.init_error


async def restart_pipeline(model: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """Restart the moderation pipeline and return its availability state."""

    logger.info("[AI PIPELINE] Restart requested; shutting down current pipeline…")
    try:
        await moderation_processor.shutdown()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[AI PIPELINE] Shutdown during restart raised: %s", exc, exc_info=True)

    model_state.available = False
    model_state.init_error = None

    logger.info("[AI PIPELINE] Re-initializing moderation pipeline…")
    await moderation_processor.init_model(model)
    await moderation_processor.start_batch_worker()
    return model_state.available, model_state.init_error


async def shutdown_pipeline() -> None:
    """Tear down the moderation pipeline and release its resources."""

    logger.info("[AI PIPELINE] Shutting down moderation pipeline…")
    await moderation_processor.shutdown()
