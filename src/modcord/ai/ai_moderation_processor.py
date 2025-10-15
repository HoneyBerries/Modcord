"""High-level orchestration logic for AI-driven moderation workflows."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional, Sequence

from modcord.ai.ai_core import InferenceProcessor, inference_processor
from modcord.util.logger import get_logger
from modcord.util.moderation_datatypes import ActionData, ActionType, ModerationBatch, ModerationMessage
import modcord.util.moderation_parsing as moderation_parsing
from modcord.configuration.app_configuration import app_config


logger = get_logger("ai_moderation_processor")


class ModerationProcessor:
    """Coordinate moderation prompts, inference, and response parsing.

    This high-level processor composes system and user prompts, delegates
    generation to a low-level InferenceProcessor, and parses the model output
    into actionable moderation decisions.
    """

    def __init__(self, engine: Optional[InferenceProcessor] = None) -> None:
        """Initialize the processor with an inference backend.

        Parameters
        ----------
        engine:
            Optional inference backend to delegate generation calls to.
        """
        self.inference_processor = engine or inference_processor
        self._shutdown: bool = False

    # ======== Engine Lifecycle ========
    async def init_model(self, model: Optional[str] = None) -> bool:
        """Initialize the inference engine and report availability."""
        self._shutdown = False
        await self.inference_processor.init_model(model)
        available = bool(self.inference_processor.state.available)
        if not available:
            logger.warning(
                "init_model: model not available (%s)",
                self.inference_processor.state.init_error,
            )
        return available

    async def start_batch_worker(self) -> bool:
        """Warm the engine with a single lightweight generation."""
        if not self.inference_processor.state.init_started:
            if not await self.init_model():
                return False

        if getattr(self.inference_processor, "warmup_completed", False):
            return True

        try:
            prompt = "Warmup prompt: prime runtime."
            await self.inference_processor.generate_text([prompt])
            self.inference_processor.warmup_completed = True
            return True
        except Exception as exc:  # noqa: BLE001 - best-effort warmup
            logger.debug("Warmup skipped: %s", exc)
            return False

    async def submit_inference(self, messages: List[Dict[str, Any]]) -> str:
        """Submit a fully composed prompt to the inference engine.

        Parameters
        ----------
        messages:
            Sequence of chat messages formatted for the inference backend.

        Returns
        -------
        str
            Raw model response payload.
        """
        if self._shutdown:
            return "null: shutting down"

        await self.inference_processor.get_model()
        state = self.inference_processor.state
        ready = (
            state.available
            and self.inference_processor.engine is not None
            and self.inference_processor.sampling_params is not None
        )
        if not ready:
            reason = state.init_error or "AI model unavailable"
            return f"null: {reason}"

        prompt = self.messages_to_prompt(messages)
        try:
            result = await self.inference_processor.generate_text([prompt])
        except Exception as exc:  # noqa: BLE001 - surface inference errors
            logger.error("Inference error: %s", exc, exc_info=True)
            return "null: inference error"

        return result[0] if result else "null: no response"

    # ======== Prompt Construction ========
    def messages_to_prompt(self, messages: List[Dict[str, Any]]) -> str:
        """Convert structured message dictionaries into a single prompt string.

        Parameters
        ----------
        messages:
            Conversation payload to flatten for the underlying engine.

        Returns
        -------
        str
            Prompt text passed to the inference backend.
        """
        parts: List[str] = []
        for message in messages:
            role = (message.get("role") or "user").lower()
            content = str(message.get("content") or "")
            if role == "system":
                parts.append(f"[SYSTEM]\n{content.strip()}")
            elif role == "assistant":
                parts.append(f"[ASSISTANT]\n{content.strip()}")
            else:
                parts.append(f"[USER]\n{content.strip()}")
        return "\n\n".join(parts).strip()

    async def get_batch_moderation_actions(
        self,
        batch: ModerationBatch,
        server_rules: str = "",
    ) -> List[ActionData]:
        """Request moderation actions for the provided batch and server rules.

        Parameters
        ----------
        batch:
            Aggregated moderation batch derived from channel activity.
        server_rules:
            Optional server rule context to include in the prompt.

        Returns
        -------
        list[ActionData]
            Parsed moderation actions recommended by the model.
        """
        system_prompt = await self.inference_processor.get_system_prompt(server_rules)
        system_msg = {"role": "system", "content": system_prompt}
        flat_messages = batch.to_model_payload()
        grouped_users = batch.to_user_payload()
        timestamps = [
            str(value)
            for value in (msg.get("timestamp") for msg in flat_messages)
            if value
        ]
        window_start = min(timestamps) if timestamps else None
        window_end = max(timestamps) if timestamps else None

        payload = {
            "channel_id": str(batch.channel_id),
            "message_count": len(flat_messages),
            "unique_user_count": len(grouped_users),
            "window_start": window_start,
            "window_end": window_end,
            "messages": flat_messages,
            "users": grouped_users,
        }
        user_msg = {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}
        resp = await self.submit_inference([system_msg, user_msg])
        logger.debug("Raw AI batch response for channel %s: %s", batch.channel_id, resp)

        parsed_actions = await moderation_parsing.parse_batch_actions(resp, batch.channel_id)

        parsed_by_user: Dict[str, ActionData] = {}
        for action in parsed_actions:
            user_key = action.user_id.strip()
            if not user_key:
                continue

            existing = parsed_by_user.get(user_key)
            if existing is None:
                parsed_by_user[user_key] = ActionData(
                    user_key,
                    action.action,
                    action.reason,
                    list(action.message_ids),
                    action.timeout_duration,
                    action.ban_duration,
                )
                continue

            if existing.action == ActionType.NULL and action.action != ActionType.NULL:
                existing.action = action.action
                existing.reason = action.reason
            elif action.action != ActionType.NULL and action.reason:
                existing.reason = action.reason

            existing.add_message_ids(*action.message_ids)

            if action.timeout_duration is not None:
                existing.timeout_duration = action.timeout_duration
            if action.ban_duration is not None:
                existing.ban_duration = action.ban_duration

        user_message_ids: Dict[str, List[str]] = {}
        user_order: List[str] = []
        for message in batch.messages:
            user_id = str(message.user_id).strip()
            if not user_id:
                continue
            if user_id not in user_order:
                user_order.append(user_id)
            user_message_ids.setdefault(user_id, [])
            message_id = str(message.message_id).strip()
            if message_id and message_id not in user_message_ids[user_id]:
                user_message_ids[user_id].append(message_id)

        final_actions: List[ActionData] = []
        for user_id in user_order:
            source = parsed_by_user.get(user_id)
            if source is None:
                reason = "no action"
                source = ActionData(user_id, ActionType.NULL, reason)

            action = ActionData(
                user_id,
                source.action,
                source.reason,
                list(source.message_ids),
                source.timeout_duration,
                source.ban_duration,
            )

            action.add_message_ids(*user_message_ids.get(user_id, []))

            final_actions.append(action)

        # Include any AI-provided actions for users not present in the batch payload as a defensive measure.
        for user_id, action in parsed_by_user.items():
            if user_id in user_order:
                continue
            final_actions.append(
                ActionData(
                    user_id,
                    action.action,
                    action.reason,
                    list(action.message_ids),
                    action.timeout_duration,
                    action.ban_duration,
                )
            )

        return final_actions

    async def shutdown(self) -> None:
        """Gracefully stop the moderation processor and unload the AI model."""

        if self._shutdown:
            logger.debug("ModerationProcessor.shutdown called multiple times")
            return

        self._shutdown = True

        # Unload the AI model
        try:
            await self.inference_processor.unload_model()
        except Exception as exc:  # noqa: BLE001 - best-effort cleanup
            logger.warning("Failed to unload AI model cleanly: %s", exc, exc_info=True)

    async def get_appropriate_action(
        self,
        history: Sequence[ModerationMessage],
        user_id: int,
        *,
        current_message: Optional[str] = None,
        server_rules: str = "",
        channel_id: Optional[int | str] = None,
        username: Optional[str] = None,
        message_timestamp: Optional[str] = None,
    ) -> tuple[ActionType, str]:
        """Assess a single message in context and return (ActionType, reason).

        The method constructs a history payload, submits it to the model, and
        parses the assistant reply into a concrete action and reason string.
        """
        message_to_assess = current_message or (history[-1].content if history else "")

        if not history and not message_to_assess.strip():
            return ActionType.NULL, "empty history"

        if not message_to_assess.strip():
            return ActionType.NULL, "empty message"

        system_prompt = await self.inference_processor.get_system_prompt(server_rules)
        system_msg = {"role": "system", "content": system_prompt}

        import datetime
        if message_timestamp:
            now_iso = message_timestamp
        else:
            now_iso = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
        payload_messages = [msg.to_history_payload() for msg in history]
        payload_messages.append(
            {
                "role": "user",
                "user_id": str(user_id),
                "username": username or f"user_{user_id}",
                "timestamp": now_iso,
                "content": message_to_assess,
            }
        )

        payload = {
            "channel_id": str(channel_id) if channel_id else "unknown",
            "messages": payload_messages,
        }
        user_msg = {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}

        assistant_response = await self.submit_inference([system_msg, user_msg])
        return await moderation_parsing.parse_action(assistant_response)


moderation_processor = ModerationProcessor()
model_state = inference_processor.state
