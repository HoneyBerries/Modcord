"""
Fully async, self-contained vLLM-backed AI model module for moderation.
Includes model initialization, inference, warmup, and JSON parsing.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

import torch
from vllm import LLM, SamplingParams
from vllm.sampling_params import GuidedDecodingParams

import modcord.configuration.app_configuration as cfg
from modcord.util.moderation_models import ActionData, ActionType, ModerationBatch, ModerationMessage
from modcord.util.logger import get_logger
import modcord.util.moderation_parsing as moderation_parsing

logger = get_logger("ai_core")

# ========= State Containers =========


class ModelState:
    def __init__(self) -> None:
        self.init_started: bool = False
        self.available: bool = False
        self.init_error: Optional[str] = None


class ModerationProcessor:
    """Encapsulates the end-to-end AI moderation workflow."""

    def __init__(self) -> None:
        self.llm: Optional[LLM] = None
        self.sampling_params: Optional[SamplingParams] = None
        self.base_system_prompt: Optional[str] = None
        self.state = ModelState()
        self.init_lock = asyncio.Lock()
        self.warmup_completed: bool = False

    # ======== Model Initialization ========
    async def init_model(self, model: Optional[str] = None) -> Tuple[Optional[LLM], Optional[SamplingParams], Optional[str]]:
        async with self.init_lock:
            if self.state.available and self.llm is not None and self.sampling_params is not None:
                return self.llm, self.sampling_params, self.base_system_prompt

            if self.state.init_started and not self.state.available and self.state.init_error:
                return self.llm, self.sampling_params, self.base_system_prompt

            self.state.init_started = True

            base_configuration = cfg.app_config.reload()
            if not base_configuration:
                logger.error("[AI MODEL] Configuration is empty; cannot initialize AI model.")
                self.state.init_error = "missing configuration"
                self.state.available = False
                return None, None, None

            self.base_system_prompt = cfg.app_config.system_prompt_template
            ai_configuration = cfg.app_config.ai_settings
            is_ai_enabled = bool(ai_configuration.get("enabled", False))
            is_gpu_allowed = bool(ai_configuration.get("allow_gpu", False))
            vram_percentage = ai_configuration.get("vram_percentage", 0.5)
            model_identifier = model or ai_configuration.get("model_id")

            knobs = ai_configuration.get("knobs", {})
            dtype = knobs.get("dtype", "auto")
            max_new_tokens = knobs.get("max_new_tokens", 256)
            max_model_length = knobs.get("max_model_length", 2048)
            temperature = knobs.get("temperature", 1.0)
            top_p = knobs.get("top_p", 1.0)
            top_k = knobs.get("top_k", -1)
            repetition_penalty = knobs.get("repetition_penalty", 1.0)
            presence_penalty = knobs.get("presence_penalty", 0.0)
            frequency_penalty = knobs.get("frequency_penalty", 0.0)

            logger.info("[AI MODEL] Using configuration knobs")
            logger.debug(
                "temperature=%s, max_new_tokens=%s, dtype=%s, top_p=%s, top_k=%s, "
                "repetition_penalty=%s, presence_penalty=%s, frequency_penalty=%s",
                temperature,
                max_new_tokens,
                dtype,
                top_p,
                top_k,
                repetition_penalty,
                presence_penalty,
                frequency_penalty,
            )

            if not is_ai_enabled:
                logger.info("[AI MODEL] AI disabled in configuration.")
                self.state.available = False
                self.state.init_error = "AI disabled in config"
                return None, None, self.base_system_prompt

            if not model_identifier:
                logger.error("[AI MODEL] No model identifier provided.")
                self.state.available = False
                self.state.init_error = "missing model id"
                return None, None, self.base_system_prompt

            cuda_available = torch.cuda.is_available()
            tp: int = torch.cuda.device_count() if cuda_available else 0

            if is_gpu_allowed and not cuda_available:
                logger.warning("[AI MODEL] GPU allowed but CUDA not available. Using CPU.")

            try:
                gpu_mem_util = vram_percentage if is_gpu_allowed and cuda_available else 0.0
                logger.info(
                    "[AI MODEL] Loading vLLM model '%s' (dtype=%s, tp=%s, gpu_mem=%s)",
                    model_identifier,
                    dtype,
                    tp,
                    gpu_mem_util,
                )
                logger.info(
                    "[AI MODEL] Config: max_model_len=%s, temperature=%s, top_p=%s",
                    max_model_length,
                    temperature,
                    top_p,
                )

                self.llm = LLM(
                    model=model_identifier,
                    dtype=dtype,
                    gpu_memory_utilization=gpu_mem_util,
                    max_model_len=max_model_length,
                    tensor_parallel_size=tp,
                )

                self.sampling_params = SamplingParams(
                    temperature=temperature,
                    max_tokens=max_new_tokens,
                    top_p=top_p,
                    top_k=top_k,
                    repetition_penalty=repetition_penalty,
                    presence_penalty=presence_penalty,
                    frequency_penalty=frequency_penalty,
                    guided_decoding=GuidedDecodingParams(json=moderation_parsing.moderation_schema),
                )

                self.state.available = True
                self.state.init_error = None
                logger.info("[AI MODEL] vLLM initialized successfully.")
                return self.llm, self.sampling_params, self.base_system_prompt

            except Exception as e:
                self.state.available = False
                self.state.init_error = f"Initialization failed: {e}"
                logger.error(f"[AI MODEL] Failed to initialize vLLM model: {e}", exc_info=True)
                return None, None, self.base_system_prompt

    async def get_model(self) -> Tuple[Optional[LLM], Optional[SamplingParams], Optional[str]]:
        if self.llm is None and not self.state.init_started:
            await self.init_model()
        return self.llm, self.sampling_params, self.base_system_prompt

    async def is_model_available(self) -> bool:
        return self.state.available

    async def get_model_init_error(self) -> Optional[str]:
        return self.state.init_error

    async def get_system_prompt(self, server_rules: str = "") -> str:
        await self.get_model()
        template = self.base_system_prompt or cfg.app_config.system_prompt_template
        return cfg.app_config.format_system_prompt(server_rules, template_override=template)

    # ======== Inference Helpers ========
    async def messages_to_prompt(self, messages: List[Dict[str, Any]]) -> str:
        parts = []
        for m in messages:
            role = (m.get("role") or "user").lower()
            content = str(m.get("content") or "")
            if role == "system":
                parts.append(f"[SYSTEM]\n{content.strip()}")
            elif role == "assistant":
                parts.append(f"[ASSISTANT]\n{content.strip()}")
            else:
                parts.append(f"[USER]\n{content.strip()}")
        return "\n\n".join(parts).strip()

    def sync_generate(self, prompts: List[str]) -> List[str]:
        if self.llm is None or self.sampling_params is None:
            raise RuntimeError("Model not initialized")

        outputs = self.llm.generate(prompts, self.sampling_params)
        results = []
        for out in outputs:
            results.append(out.outputs[0].text.strip() if out.outputs else "")
        return results

    async def submit_inference(self, messages: List[Dict[str, Any]]) -> str:
        if self.state.init_started and not self.state.available:
            reason = self.state.init_error or "AI model unavailable"
            logger.debug(f"Short-circuiting inference; {reason}")
            return f"null: {reason}"

        model, params, _ = await self.get_model()
        if model is None or params is None:
            reason = self.state.init_error or "AI model unavailable"
            logger.debug(f"Inference skipped; model not ready ({reason})")
            return f"null: {reason}"

        prompt = await self.messages_to_prompt(messages)

        try:
            results = await asyncio.to_thread(self.sync_generate, [prompt])
            return results[0] if results else "null: no response"
        except Exception as e:
            logger.error(f"Inference error: {e}", exc_info=True)
            return f"null: inference error"

    async def start_batch_worker(self) -> None:

        async def warmup(self) -> None:
            if self.warmup_completed:
                return

            logger.info("Warming up model...")
            model, params, _ = await self.get_model()
            if model is None or params is None:
                logger.info("Skipping warmup; model unavailable (%s)", self.state.init_error or "no error")
                return
        
        if not self.state.init_started:
            await self.init_model()
        try:
            asyncio.create_task(warmup(self))
        except RuntimeError:
            logger.debug("start_batch_worker called outside event loop; skipping warmup task.")


    # ======== Public Moderation Entrypoints ========
    async def get_batch_moderation_actions(
        self,
        batch: ModerationBatch,
        server_rules: str = "",
    ) -> List[ActionData]:
        system_prompt = await self.get_system_prompt(server_rules)
        system_msg = {"role": "system", "content": system_prompt}
        payload = {"channel_id": str(batch.channel_id), "messages": batch.to_model_payload()}
        user_msg = {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}
        resp = await self.submit_inference([system_msg, user_msg])

        # Parse whatever the model returned (may be sparse) and then ensure we have
        # exactly one action for every input message. If the model omitted an
        # action for a message, insert the no-op action 'null'.
        parsed_actions = await moderation_parsing.parse_batch_actions(resp, batch.channel_id)

        # Build quick lookup maps from message_id -> action and user_id -> action
        msgid_map: Dict[str, ActionData] = {}
        userid_map: Dict[str, ActionData] = {}
        for action in parsed_actions:
            u = action.user_id.strip()
            mids = action.message_ids or []
            if mids:
                for mid in mids:
                    mid_s = str(mid).strip()
                    if mid_s:
                        msgid_map[mid_s] = action
            elif u:
                userid_map.setdefault(u, action)

        final_actions: List[ActionData] = []
        for msg in batch.messages:
            mid = msg.message_id
            uid = msg.user_id

            source: Optional[ActionData] = None
            if mid and mid in msgid_map:
                source = msgid_map[mid]
            elif uid and uid in userid_map:
                source = userid_map[uid]

            if source is None:
                action = ActionData(
                    user_id=uid,
                    action=ActionType.NULL,
                    reason="no action",
                    message_ids=[mid] if mid else [],
                    timeout_duration=None,
                    ban_duration=None,
                )
            else:
                action = ActionData(
                    user_id=source.user_id or uid,
                    action=source.action,
                    reason=source.reason,
                    message_ids=list(source.message_ids),
                    timeout_duration=source.timeout_duration,
                    ban_duration=source.ban_duration,
                )

            if mid:
                action.add_message_ids(mid)
            if not action.user_id and uid:
                action.user_id = uid

            final_actions.append(action)

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
        message_to_assess = current_message or (history[-1].content if history else "")

        if not history and not message_to_assess.strip():
            return ActionType.NULL, "empty history"

        if not message_to_assess.strip():
            return ActionType.NULL, "empty message"

        system_prompt = await self.get_system_prompt(server_rules)
        system_msg = {"role": "system", "content": system_prompt}

        now_iso = message_timestamp or time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
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
    
    def get_model_state(self) -> ModelState:
        return self.state


moderation_processor = ModerationProcessor()
model_state = moderation_processor.state