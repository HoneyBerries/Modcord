"""High-level orchestration logic for AI-driven moderation workflows."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

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
        """Initialize the processor with an inference backend and local caches.

        Parameters
        ----------
        engine:
            Optional inference backend to delegate generation calls to.
        """
        self.inference_processor = engine or inference_processor
        self._inference_queue: asyncio.Queue[Tuple[str, asyncio.Future[str]]] = asyncio.Queue()
        self._inference_worker: Optional[asyncio.Task[None]] = None
        self._shutdown: bool = False

        # Load batching knobs from configuration with safe defaults.
        batching_cfg = app_config.ai_settings.batching if app_config else {}

        try:
            self._batch_max_prompts = max(1, int(batching_cfg.get("max_prompts", 8)))
        except Exception:
            self._batch_max_prompts = 8

        try:
            self._batch_max_delay = max(0.0, float(batching_cfg.get("max_delay", 0.2)))
        except Exception:
            self._batch_max_delay = 0.2  # seconds

        logger.info(
            "Inference batching configured: max_prompts=%d, max_delay=%.3fs",
            self._batch_max_prompts,
            self._batch_max_delay,
        )

    # ======== Engine Lifecycle ========
    async def init_model(self, model: Optional[str] = None) -> bool:
        """Initialize the inference engine and return its availability state.

        Parameters
        ----------
        model:
            Optional model identifier to override the configured default.

        Returns
        -------
        bool
            ``True`` when the engine is ready to accept requests.
        """
        self._shutdown = False
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
        """Start any background workers needed to service queued inferences."""
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
                            import datetime
                            now_iso = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
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
            self._ensure_inference_batch_worker()
            return True
        except RuntimeError as re:
            # Called outside an event loop, cannot schedule background task
            logger.debug("start_batch_worker called outside event loop; skipping warmup task scheduling. Error: %s", re)
            return False
        except Exception as exc:
            logger.error("Failed to schedule warmup task: %s", exc, exc_info=True)
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
            logger.debug("submit_inference called during shutdown; returning null response")
            return "null: shutting down"

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
        self._ensure_inference_batch_worker()
        try:
            result = await self._enqueue_prompt_for_inference(prompt)
            return result if result else "null: no response"
        except RuntimeError as err:
            logger.debug("Inference aborted: %s", err)
            return f"null: {err}"
        except Exception as exc:  # noqa: BLE001 - bubble inference errors
            logger.error("Inference error: %s", exc, exc_info=True)
            return "null: inference error"

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

    def _ensure_inference_batch_worker(self) -> None:
        """Ensure any inference queue workers are running prior to submissions."""
        if self._shutdown:
            logger.debug("Inference worker requested while shutting down; skipping creation")
            return
        if self._inference_worker and not self._inference_worker.done():
            return
        loop = asyncio.get_running_loop()
        self._inference_worker = loop.create_task(
            self._batched_inference_worker(),
            name="moderation-batched-inference",
        )

    async def _enqueue_prompt_for_inference(self, prompt: str) -> str:
        """Enqueue a prompt for inference and await the generated response.

        Parameters
        ----------
        prompt:
            Fully rendered prompt text destined for the inference queue.

        Returns
        -------
        str
            Raw model output returned by the inference worker.
        """
        loop = asyncio.get_running_loop()
        future: "asyncio.Future[str]" = loop.create_future()
        await self._inference_queue.put((prompt, future))
        return await future

    async def _batched_inference_worker(self) -> None:
        try:
            while True:
                try:
                    prompt, future = await self._inference_queue.get()
                except asyncio.CancelledError:
                    logger.debug("Inference worker cancelled while awaiting queue item")
                    break

                prompts = [prompt]
                futures = [future]

                start = time.monotonic()
                while len(prompts) < self._batch_max_prompts:
                    remaining = self._batch_max_delay - (time.monotonic() - start)
                    if remaining <= 0:
                        break
                    try:
                        next_prompt, next_future = await asyncio.wait_for(self._inference_queue.get(), remaining)
                        prompts.append(next_prompt)
                        futures.append(next_future)
                    except asyncio.TimeoutError:
                        break
                    except asyncio.CancelledError:
                        logger.debug("Inference worker cancelled during batch aggregation")
                        break

                wait_duration = time.monotonic() - start
                queue_remaining = self._inference_queue.qsize()
                logger.info(
                    "Dispatching inference batch: size=%d, wait=%.3fs, remaining_queue=%d",
                    len(prompts),
                    wait_duration,
                    queue_remaining,
                )

                try:
                    if hasattr(self.inference_processor, "generate_text"):
                        results = await self.inference_processor.generate_text(prompts)  # type: ignore[arg-type]
                    else:
                        results = await asyncio.to_thread(self.inference_processor.sync_generate, prompts)
                except Exception as exc:  # noqa: BLE001
                    for fut in futures:
                        if not fut.done():
                            fut.set_exception(exc)
                    continue

                if results is None or len(results) != len(futures):
                    error = RuntimeError("Inference outputs did not match request count")
                    for fut in futures:
                        if not fut.done():
                            fut.set_exception(error)
                    continue

                for fut, output in zip(futures, results):
                    if not fut.done():
                        fut.set_result(output)
        except asyncio.CancelledError:
            logger.debug("Inference worker task cancelled")
        finally:
            drained = 0
            while not self._inference_queue.empty():
                try:
                    _, future = self._inference_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                else:
                    drained += 1
                    if not future.done():
                        future.set_result("null: shutting down")
            if drained:
                logger.debug("Inference worker drained %d queued prompts during shutdown", drained)

    async def shutdown(self) -> None:
        """Gracefully stop background inference processing."""

        if self._shutdown:
            logger.debug("ModerationProcessor.shutdown called multiple times")
            return

        self._shutdown = True

        worker = self._inference_worker
        if worker and not worker.done():
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Inference worker raised during shutdown")

        self._inference_worker = None

        drained = 0
        while not self._inference_queue.empty():
            try:
                _, future = self._inference_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            else:
                drained += 1
                if not future.done():
                    future.set_result("null: shutting down")
        if drained:
            logger.debug("Rejected %d pending inference requests during shutdown", drained)

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
