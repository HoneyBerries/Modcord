"""High-level orchestration logic for AI-driven moderation workflows."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence

from modcord.ai.ai_core import InferenceProcessor, inference_processor
from modcord.util.logger import get_logger
from modcord.util.moderation_datatypes import ActionData, ActionType, ModerationBatch, ModerationMessage
import modcord.util.moderation_parsing as moderation_parsing
from modcord.configuration.app_configuration import app_config


logger = get_logger("ai_moderation_processor")


class ModerationProcessor:
    """Coordinate moderation prompts, inference, and response parsing."""

    def __init__(self, engine: Optional[InferenceProcessor] = None) -> None:
        self.inference_processor = engine or inference_processor
        self._shutdown = False

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
        if not await self._ensure_model_initialized():
            return False
        return await self._warmup_engine()

    async def submit_inference(self, messages: List[Dict[str, Any]]) -> str:
        """Submit a fully composed prompt to the inference engine."""
        if self._shutdown:
            return "null: shutting down"

        ok, reason = await self._ensure_model_available()
        if not ok:
            return f"null: {reason}"

        prompt = await self.messages_to_prompt(messages)
        logger.debug("Final prompt sent to model (first 500 chars): %s", repr(prompt[:500]))
        try:
            results = await self.inference_processor.generate_text([prompt])
        except Exception as exc:
            logger.error("Inference error: %s", exc, exc_info=True)
            return "null: inference error"

        if not results:
            logger.warning("Inference returned no results")
            return "null: no response"

        if len(results) != 1:
            logger.warning("Expected single inference result, received %d", len(results))

        return (results[0] or "").strip()

    # ======== Helpers: Engine ========
    async def _ensure_model_initialized(self) -> bool:
        """Ensure the model has been initialized at least once."""
        if not self.inference_processor.state.init_started:
            return await self.init_model()
        return True

    async def _warmup_engine(self) -> bool:
        """Perform a warmup generation once."""
        if getattr(self.inference_processor, "warmup_completed", False):
            return True
        try:
            await self.inference_processor.generate_text(["Warmup prompt: prime runtime."])
            self.inference_processor.warmup_completed = True
            return True
        except Exception as exc:
            logger.debug("Warmup skipped: %s", exc)
            return False

    async def _ensure_model_available(self) -> tuple[bool, str]:
        """Check model availability and return (ok, reason_if_not_ok)."""
        await self.inference_processor.get_model()
        state = self.inference_processor.state
        ready = (
            state.available
            and self.inference_processor.engine is not None
            and self.inference_processor.sampling_params is not None
        )
        return (True, "") if ready else (False, state.init_error or "AI model unavailable")

    # ======== Helpers: Prompt Construction ========
    async def messages_to_prompt(self, messages: List[Dict[str, Any]]) -> str:
        """Convert message dicts to a prompt string using the tokenizer's chat template.
        
        Uses Qwen3's official chat template for proper message formatting.
        """
        engine = self.inference_processor.engine
        if not engine or not hasattr(engine, 'get_tokenizer'):
            logger.error("Engine or tokenizer not available for chat template")
            raise RuntimeError("Model engine not properly initialized")
        
        tokenizer = await engine.get_tokenizer()
        prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )
        return prompt.strip()

    def _resolve_server_rules(self, server_rules: str = "") -> str:
        """Pick guild-specific rules when provided, otherwise fall back to global defaults."""
        base_rules = (app_config.server_rules or "").strip()
        guild_rules = (server_rules or "").strip()
        resolved = guild_rules or base_rules
        logger.debug("Resolved server rules: guild_rules_len=%d, base_rules_len=%d, using=%s", 
                     len(guild_rules), len(base_rules), "guild" if guild_rules else "base")
        return resolved

    async def _infer_json(self, payload: Dict[str, Any], server_rules: str = "") -> str:
        """Compose system+user messages from JSON payload and submit inference."""
        merged_rules = self._resolve_server_rules(server_rules)
        system_prompt = await self.inference_processor.get_system_prompt(merged_rules)

        # Debug logging to verify system prompt is properly injected
        logger.debug("System prompt length: %d chars, contains placeholder: %s, contains server rules: %s",
            len(system_prompt),
            "<|SERVER_RULES_INJECT|>" in system_prompt,
            "No hate speech" in system_prompt or "discrimination" in system_prompt)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        return await self.submit_inference(messages)


    # ======== Business Logic ========
    async def get_batch_moderation_actions(
        self,
        batch: ModerationBatch,
        server_rules: str = "",
    ) -> List[ActionData]:
        """Request moderation actions for the provided batch and server rules."""
        payload, user_order, user_message_ids = self._build_batch_payload(batch)

        user_msg_content = json.dumps(payload, ensure_ascii=False)
        logger.debug("Raw moderation batch input JSON for channel %s: %s", batch.channel_id, user_msg_content)

        resp = await self._infer_json(payload, server_rules)

        logger.debug("Raw AI batch response for channel %s: %s", batch.channel_id, resp)

        parsed_actions = await moderation_parsing.parse_batch_actions(resp, batch.channel_id)
        final_actions = self._finalize_batch_actions(parsed_actions, user_order, user_message_ids)
        return final_actions

    async def shutdown(self) -> None:
        """Gracefully stop the moderation processor and unload the AI model."""
        if self._shutdown:
            logger.debug("ModerationProcessor.shutdown called multiple times")
            return

        self._shutdown = True

        try:
            await self.inference_processor.unload_model()
        except Exception as exc:
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
        """Assess a single message in context and return (ActionType, reason)."""
        message_to_assess = current_message or (history[-1].content if history else "")

        if not history and not message_to_assess.strip():
            return ActionType.NULL, "empty history"

        if not message_to_assess.strip():
            return ActionType.NULL, "empty message"

        now_iso = message_timestamp or self._now_iso()
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

        assistant_response = await self._infer_json(payload, server_rules)
        return await moderation_parsing.parse_action(assistant_response)

    # ======== Internal: Batch payload and action merging ========
    def _build_batch_payload(
        self,
        batch: ModerationBatch,
    ) -> tuple[Dict[str, Any], List[str], Dict[str, List[str]]]:
        """Build the AI payload for a batch and track ordering/id maps."""
        users_payload: Dict[str, Dict[str, Any]] = {}
        user_message_ids: Dict[str, List[str]] = {}
        user_order: List[str] = []
        window_start: Optional[str] = None
        window_end: Optional[str] = None

        flat_messages: List[Dict[str, Any]] = []

        for message in batch.messages:
            timestamp_value = str(message.timestamp).strip() if message.timestamp else ""
            if timestamp_value:
                window_start = timestamp_value if window_start is None else min(window_start, timestamp_value)
                window_end = timestamp_value if window_end is None else max(window_end, timestamp_value)

            user_id = str(message.user_id).strip()
            if not user_id:
                continue

            if user_id not in users_payload:
                users_payload[user_id] = {
                    "username": str(message.username or ""),
                    "messages": [],
                    "first_message_timestamp": None,
                    "latest_message_timestamp": None,
                }
                user_message_ids[user_id] = []
                user_order.append(user_id)

            entry = users_payload[user_id]
            if timestamp_value:
                if entry["first_message_timestamp"] is None:
                    entry["first_message_timestamp"] = timestamp_value
                entry["latest_message_timestamp"] = timestamp_value
            entry["messages"].append(
                {
                    "message_id": str(message.message_id),
                    "content": str(message.content or ""),
                    "timestamp": timestamp_value or None,
                }
            )

            message_id = str(message.message_id).strip()
            if message_id and message_id not in user_message_ids[user_id]:
                user_message_ids[user_id].append(message_id)

            flat_messages.append(
                {
                    "message_id": str(message.message_id),
                    "user_id": user_id,
                    "username": str(message.username or ""),
                    "timestamp": timestamp_value or None,
                    "content": str(message.content or ""),
                    "image_summary": message.image_summary,
                    "role": message.role,
                    "is_context": False,
                }
            )

        for entry in users_payload.values():
            entry["message_count"] = len(entry["messages"])

        history_messages: List[Dict[str, Any]] = []
        if batch.history:
            for history_entry in batch.history:
                history_messages.append(
                    {
                        "message_id": str(history_entry.message_id),
                        "user_id": str(history_entry.user_id),
                        "username": str(history_entry.username or ""),
                        "timestamp": str(history_entry.timestamp or "") or None,
                        "content": str(history_entry.content or ""),
                        "image_summary": history_entry.image_summary,
                        "role": history_entry.role,
                        "is_context": True,
                    }
                )

        payload = {
            "channel_id": str(batch.channel_id),
            "window_start": window_start,
            "window_end": window_end,
            "message_count": len(flat_messages),
            "unique_user_count": len(user_order),
            "messages": flat_messages,
            "users": users_payload,
        }
        if history_messages:
            payload["history"] = history_messages
            payload["history_count"] = len(history_messages)
        return payload, user_order, user_message_ids

    def _finalize_batch_actions(
        self,
        parsed_actions: List[ActionData],
        user_order: List[str],
        user_message_ids: Dict[str, List[str]],
    ) -> List[ActionData]:
        """Merge, order, and reconcile AI actions with actual messages."""
        parsed_by_user: Dict[str, ActionData] = {}
        for action in parsed_actions:
            user_key = action.user_id.strip()
            if not user_key:
                continue
            parsed_by_user[user_key] = self._merge_action(parsed_by_user.get(user_key), action)

        final_actions: List[ActionData] = []
        for user_id in user_order:
            source = parsed_by_user.get(user_id) or ActionData(user_id, ActionType.NULL, "no action")
            actual_ids = list(user_message_ids.get(user_id, []))
            ai_ids = [mid.strip() for mid in source.message_ids if mid]
            valid_ai_ids = [mid for mid in ai_ids if mid in actual_ids]

            if ai_ids and not valid_ai_ids and actual_ids:
                fallback_count = min(len(ai_ids), len(actual_ids))
                valid_ai_ids = actual_ids[-fallback_count:]

            if ai_ids and not valid_ai_ids and not actual_ids:
                logger.debug(
                    "No matching batch messages for AI-provided ids %s (user %s)",
                    ai_ids,
                    user_id,
                )

            message_ids = valid_ai_ids or actual_ids
            final_actions.append(
                ActionData(
                    user_id,
                    source.action,
                    source.reason,
                    list(message_ids),
                    source.timeout_duration,
                    source.ban_duration,
                )
            )

        # Include any extra users the AI mentioned that weren't in the batch.
        for user_id, action in parsed_by_user.items():
            if user_id not in user_order:
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

    @staticmethod
    def _merge_action(existing: Optional[ActionData], new: ActionData) -> ActionData:
        """Merge two ActionData objects conservatively."""
        if existing is None:
            return ActionData(
                new.user_id,
                new.action,
                new.reason,
                list(new.message_ids),
                new.timeout_duration,
                new.ban_duration,
            )

        # Prefer non-NULL action; use latest non-empty reason for non-NULL actions
        if existing.action == ActionType.NULL and new.action != ActionType.NULL:
            existing.action = new.action
            existing.reason = new.reason
        elif new.action != ActionType.NULL and new.reason:
            existing.reason = new.reason

        existing.add_message_ids(*new.message_ids)

        if new.timeout_duration is not None:
            existing.timeout_duration = new.timeout_duration
        if new.ban_duration is not None:
            existing.ban_duration = new.ban_duration

        return existing

    @staticmethod
    def _now_iso() -> str:
        import datetime
        return (
            datetime.datetime.now(datetime.timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )


moderation_processor = ModerationProcessor()
model_state = inference_processor.state