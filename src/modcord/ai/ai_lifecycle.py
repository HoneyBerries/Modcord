"""Lifecycle management helpers for the AI moderation engine."""
from __future__ import annotations

from typing import Optional, Tuple

from modcord.ai.ai_core import ModelState
from modcord.ai.ai_moderation_processor import ModerationProcessor, moderation_processor, model_state
from modcord.util.logger import get_logger

logger = get_logger("ai_lifecycle")


class AIEngineLifecycle:
    """Manage initialization, restart, and shutdown of the moderation engine."""

    def __init__(self, processor: ModerationProcessor, state: ModelState) -> None:
        """Bind the lifecycle controller to the shared processor and model state."""
        self._processor = processor
        self._state = state

    async def initialize(self, model: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """Initialize the moderation engine and report availability status."""

        logger.info("[AI LIFECYCLE] Initializing moderation engine…")
        await self._processor.init_model(model)
        await self._processor.start_batch_worker()
        return self._state.available, self._state.init_error

    async def restart(self, model: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """Reinitialize the moderation engine without tearing down the bot."""

        logger.info("[AI LIFECYCLE] Restart requested; shutting down current engine…")
        try:
            await self._processor.shutdown()
        except Exception as exc:
            logger.warning(
                "[AI LIFECYCLE] Shutdown during restart raised: %s",
                exc,
                exc_info=True,
            )

        self._state.available = False
        self._state.init_error = None

        logger.info("[AI LIFECYCLE] Re-initializing moderation engine…")
        await self._processor.init_model(model)
        await self._processor.start_batch_worker()
        return self._state.available, self._state.init_error

    async def shutdown(self) -> None:
        """Shutdown the moderation engine and release any held resources."""

        logger.info("[AI LIFECYCLE] Shutting down moderation engine…")
        await self._processor.shutdown()


ai_engine_lifecycle = AIEngineLifecycle(moderation_processor, model_state)


async def initialize_engine(model: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """Module-level helper mirroring :meth:`AIEngineLifecycle.initialize`."""

    return await ai_engine_lifecycle.initialize(model)


async def restart_engine(model: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """Module-level helper mirroring :meth:`AIEngineLifecycle.restart`."""

    return await ai_engine_lifecycle.restart(model)


async def shutdown_engine() -> None:
    """Module-level helper mirroring :meth:`AIEngineLifecycle.shutdown`."""

    await ai_engine_lifecycle.shutdown()
