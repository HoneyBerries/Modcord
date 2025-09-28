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

    def __init__(self, engine: InferenceProcessor) -> None:
        """Create a ModerationProcessor.

        Args:
            engine: InferenceProcessor to use; defaults to the module-level
                    inference_processor if not provided.
        """
        self.inference_processor = inference_processor

    # ======== Engine Lifecycle ========
    async def init_model(self, model: Optional[str] = None) -> bool:
        """Initialize or reload the underlying AI model.

        Returns:
            True if initialization succeeded (model available), False otherwise.
        """
        try:
            # Forward to inference_processor; it may return different payloads but state is authoritative.
            await self.inference_processor.init_model(model)
            available = bool(getattr(self.inference_processor.state, "available", False))
            if available:
                logger.info("init_model: model available")
            else:
                logger.warning("init_model: model not available (%s)", getattr(self.inference_processor.state, "init_error", None))
            return available
        except Exception as exc:
            logger.error("Model initialization failed: %s", exc, exc_info=True)
            return False

    async def start_batch_worker(self) -> bool:
        """Kick off a background warmup task for the model.

        Returns:
            True if the warmup task was scheduled (or already completed),
            False if skipped or if scheduling failed immediately.
        """

        async def warmup() -> bool:
            """Perform a warmup generation if not already done.

            Returns:
                True if warmup completed or already done, False if skipped or failed.
            """
            if getattr(self.inference_processor, "warmup_completed", False):
                logger.debug("warmup: already completed")
                return True

            logger.info("Warming up model...")
            model, params, _ = await self.inference_processor.get_model()
            if model is None or params is None:
                logger.info("Skipping warmup; model unavailable (%s)", self.inference_processor.state.init_error or "no error")
                return False

            # Best-effort torch.compile on underlying model if possible.
            try:
                import torch  # type: ignore

                underlying = getattr(model, "model", None)
                if underlying is not None and hasattr(torch, "compile"):
                    try:
                        logger.info("Attempting torch.compile on underlying model for JIT optimizations...")
                        compiled = torch.compile(underlying, mode="max-autotune")  # best-effort
                        # Assign back if successful — some vLLM internals may not expect mutation,
                        # but this is a best-effort optimization and non-fatal if it fails later.
                        try:
                            setattr(model, "model", compiled)
                            logger.info("torch.compile completed successfully.")
                        except Exception as assign_exc:
                            # Non-fatal: log and continue to warmup generation
                            logger.debug("Failed to assign compiled model back to vLLM wrapper: %s", assign_exc)
                    except Exception as compile_exc:
                        logger.debug("torch.compile attempted but failed: %s", compile_exc)
                else:
                    logger.debug("torch.compile not available or underlying model not found; skipping JIT.")
            except Exception:
                logger.debug("torch not importable or compile unavailable; skipping JIT compile step.")

            # Trigger a small dummy generation to force vLLM to capture CUDA graphs / do first-time work.
            try:
                dummy_prompt = "Warmup prompt: perform a short, harmless generation to prime runtime."
                # Use engine.sync_generate via thread to avoid blocking event loop if it's a blocking function.
                try:
                    await asyncio.to_thread(self.inference_processor.sync_generate, [dummy_prompt])
                except AttributeError:
                    # If engine does not expose sync_generate, fall back to engine.generate_text or submit_inference
                    if hasattr(self.inference_processor, "generate_text"):
                        try:
                            results = await self.inference_processor.generate_text([dummy_prompt])
                            logger.debug("warmup: generate_text returned %s", bool(results))
                        except Exception as gen_exc:
                            logger.warning("warmup: generate_text failed: %s", gen_exc, exc_info=True)
                            return False
                    else:
                        # Last resort: call submit_inference with simple system/user wrapper
                        try:
                            system_prompt = await self.inference_processor.get_system_prompt("")
                            system_msg = {"role": "system", "content": system_prompt}
                            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                            dummy_payload = {
                                "channel_id": "warmup",
                                "message_count": 1,
                                "unique_user_count": 1,
                                "window_start": now_iso,
                                "window_end": now_iso,
                                "messages": [
                                    {
                                        "user_id": "warmup_user",
                                        "username": "warmup",
                                        "message_id": "warmup-0",
                                        "timestamp": now_iso,
                                        "content": dummy_prompt,
                                        "image_summary": None,
                                        "role": "user",
                                    }
                                ],
                                "users": [
                                    {
                                        "user_id": "warmup_user",
                                        "username": "warmup",
                                        "message_count": 1,
                                        "first_message_timestamp": now_iso,
                                        "latest_message_timestamp": now_iso,
                                        "messages": [
                                            {
                                                "message_id": "warmup-0",
                                                "timestamp": now_iso,
                                                "content": dummy_prompt,
                                                "image_summary": None,
                                                "role": "user",
                                            }
                                        ],
                                    }
                                ],
                            }
                            user_msg = {"role": "user", "content": json.dumps(dummy_payload, ensure_ascii=False)}
                            resp = await self.submit_inference([system_msg, user_msg])
                            logger.debug("warmup: submit_inference returned length %d", len(resp) if isinstance(resp, str) else 0)
                        except Exception as si_exc:
                            logger.warning("warmup: fallback submit_inference failed: %s", si_exc, exc_info=True)
                            return False

                # If we reached here, warmup was attempted successfully
                self.inference_processor.warmup_completed = True
                logger.info("Model warmup completed successfully.")
                return True

            except Exception as e:
                logger.warning("Warmup generation failed: %s", e, exc_info=True)
                return False

        # Ensure model initialization started (best-effort)
        if not getattr(self.inference_processor.state, "init_started", False):
            init_success = await self.init_model()
            if not init_success:
                logger.info("start_batch_worker: init_model failed or reported unavailable; not scheduling warmup.")
                return False

        # Schedule warmup in background
        try:
            asyncio.create_task(warmup())
            logger.debug("start_batch_worker: warmup task scheduled")
            return True
        except RuntimeError as re:
            # Called outside an event loop, cannot schedule background task
            logger.debug("start_batch_worker called outside event loop; skipping warmup task scheduling. Error: %s", re)
            return False
        except Exception as exc:
            logger.error("Failed to schedule warmup task: %s", exc, exc_info=True)
            return False

    async def submit_inference(self, messages: List[Dict[str, Any]]) -> str:
        """Submit a sequence of role/content messages to the model and return text.

        Returns the raw assistant response string on success or a string prefixed
        with 'null:' describing the failure reason on error.
        """
        if self.inference_processor.state.init_started and not self.inference_processor.state.available:
            reason = self.inference_processor.state.init_error or "AI model unavailable"
            logger.debug("Short-circuiting inference; %s", reason)
            return f"null: {reason}"

        try:
            await self.inference_processor.get_model()
        except Exception as exc:  # noqa: BLE001 - surface init issues
            logger.error("Unexpected error acquiring model: %s", exc, exc_info=True)
            return "null: inference error"

        if (
            not self.inference_processor.state.available
            or self.inference_processor.llm is None
            or self.inference_processor.sampling_params is None
        ):
            reason = self.inference_processor.state.init_error or "AI model unavailable"
            logger.debug("Inference skipped; model not ready (%s)", reason)
            return f"null: {reason}"

        prompt = self.messages_to_prompt(messages)

        try:
            # Prefer engine.generate_text if present (async), otherwise fallback to engine.sync_generate via thread.
            if hasattr(self.inference_processor, "generate_text"):
                results = await self.inference_processor.generate_text([prompt])
            else:
                results = await asyncio.to_thread(self.inference_processor.sync_generate, [prompt])

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


moderation_processor = ModerationProcessor(inference_processor)
model_state = inference_processor.state
