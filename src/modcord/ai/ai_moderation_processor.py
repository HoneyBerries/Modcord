"""High-level orchestration logic for AI-driven moderation workflows."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Sequence

from modcord.ai.ai_core import InferenceProcessor, inference_processor
from modcord.util.logger import get_logger
from modcord.util.moderation_models import ActionData, ActionType, ModerationBatch, ModerationMessage
import modcord.util.moderation_parsing as moderation_parsing


logger = get_logger("ai_moderation_processor")


class ModerationProcessor:
    """Coordinate moderation prompts, inference, and response parsing.

    This high-level processor composes system and user prompts, delegates
    generation to a low-level InferenceProcessor, and parses the model output
    into actionable moderation decisions.
    """

    def __init__(self, engine: InferenceProcessor | None = None) -> None:
        """Create a ModerationProcessor.

        Args:
            engine: Optional InferenceProcessor to use; defaults to the module-level
                    inference_processor if not provided.
        """
        self.engine = engine or inference_processor

    # ======== Engine Lifecycle ========
    async def init_model(self, model: Optional[str] = None):
        """Initialize or reload the underlying AI model.

        The call is forwarded to the configured InferenceProcessor.
        """
        return await self.engine.init_model(model)

    async def start_batch_worker(self) -> None:
        """Kick off a background warmup task for the model.

        The warmup prepares the model so the first inference is faster. If the
        model is not initialized yet, this will trigger initialization first.
        """
        async def warmup() -> None:
            if self.engine.warmup_completed:
                return

            logger.info("Warming up model...")
            model, params, _ = await self.engine.get_model()
            if model is None or params is None:
                logger.info(
                    "Skipping warmup; model unavailable (%s)",
                    self.engine.state.init_error or "no error",
                )
                return

            self.engine.warmup_completed = True

        if not self.engine.state.init_started:
            await self.engine.init_model()
        try:
            asyncio.create_task(warmup())
        except RuntimeError:
            logger.debug(
                "start_batch_worker called outside event loop; skipping warmup task."
            )

    async def submit_inference(self, messages: List[Dict[str, Any]]) -> str:
        """Submit a sequence of role/content messages to the model and return text.

        Returns the raw assistant response string on success or a string prefixed
        with 'null:' describing the failure reason on error.
        """
        if self.engine.state.init_started and not self.engine.state.available:
            reason = self.engine.state.init_error or "AI model unavailable"
            logger.debug("Short-circuiting inference; %s", reason)
            return f"null: {reason}"

        try:
            await self.engine.get_model()
        except Exception as exc:  # noqa: BLE001 - surface init issues
            logger.error("Unexpected error acquiring model: %s", exc, exc_info=True)
            return "null: inference error"

        if (
            not self.engine.state.available
            or self.engine.llm is None
            or self.engine.sampling_params is None
        ):
            reason = self.engine.state.init_error or "AI model unavailable"
            logger.debug("Inference skipped; model not ready (%s)", reason)
            return f"null: {reason}"

        prompt = self.messages_to_prompt(messages)

        try:
            results = await self.engine.generate_text([prompt])
            return results[0] if results else "null: no response"
        except RuntimeError as err:
            logger.debug("Inference aborted: %s", err)
            return f"null: {err}"
        except Exception as exc:  # noqa: BLE001 - bubble inference errors
            logger.error("Inference error: %s", exc, exc_info=True)
            return "null: inference error"

    # ======== Prompt Construction ========
    def messages_to_prompt(self, messages: List[Dict[str, Any]]) -> str:
        """Convert role/content message dicts into a single prompt string.

        Roles are mapped to bracketed sections ([SYSTEM], [ASSISTANT], [USER]).
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
        """Run moderation on a batch and return a list of ActionData results.

        The function builds a system+user prompt describing the batch, submits it
        to the model, and parses the response into concrete moderation actions.
        """
        system_prompt = await self.engine.get_system_prompt(server_rules)
        system_msg = {"role": "system", "content": system_prompt}
        payload = {"channel_id": str(batch.channel_id), "messages": batch.to_model_payload()}
        user_msg = {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}
        resp = await self.submit_inference([system_msg, user_msg])

        parsed_actions = await moderation_parsing.parse_batch_actions(resp, batch.channel_id)

        msgid_map: Dict[str, ActionData] = {}
        userid_map: Dict[str, ActionData] = {}
        for action in parsed_actions:
            user_key = action.user_id.strip()
            message_ids = action.message_ids or []
            if message_ids:
                for mid in message_ids:
                    mid_s = str(mid).strip()
                    if mid_s:
                        msgid_map[mid_s] = action
            elif user_key:
                userid_map.setdefault(user_key, action)

        final_actions: List[ActionData] = []
        for message in batch.messages:
            message_id = message.message_id
            user_id = message.user_id

            source: Optional[ActionData] = None
            if message_id and message_id in msgid_map:
                source = msgid_map[message_id]
            elif user_id and user_id in userid_map:
                source = userid_map[user_id]

            if source is None:
                action = ActionData(user_id, ActionType.NULL, "no action", [message_id] if message_id else [], None, None)
                
            else:
                action = ActionData(source.user_id or user_id, source.action, source.reason, list(source.message_ids), source.timeout_duration, source.ban_duration)

            if message_id:
                action.add_message_ids(message_id)
            if not action.user_id and user_id:
                action.user_id = user_id

            final_actions.append(action)

        return final_actions

    async def get_appropriate_action(self, history: Sequence[ModerationMessage], user_id: int, *, current_message: Optional[str] = None, server_rules: str = "", channel_id: Optional[int | str] = None, username: Optional[str] = None, message_timestamp: Optional[str] = None) -> tuple[ActionType, str]:
        """Assess a single message in context and return (ActionType, reason).

        The method constructs a history payload, submits it to the model, and
        parses the assistant reply into a concrete action and reason string.
        """
        message_to_assess = current_message or (history[-1].content if history else "")

        if not history and not message_to_assess.strip():
            return ActionType.NULL, "empty history"

        if not message_to_assess.strip():
            return ActionType.NULL, "empty message"

        system_prompt = await self.engine.get_system_prompt(server_rules)
        system_msg = {"role": "system", "content": system_prompt}

        now_iso = message_timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
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
