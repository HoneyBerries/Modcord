"""
Fully async, self-contained vLLM-backed AI model module for moderation.
Includes model initialization, inference, warmup, and JSON parsing.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Tuple

import torch
from vllm import LLM, SamplingParams
from vllm.sampling_params import GuidedDecodingParams

import modcord.configuration.app_configuration as cfg
from modcord.util.actions import ActionType
from modcord.util.logger import get_logger

logger = get_logger("ai_model")

VALID_ACTION_VALUES: set[str] = {action.value for action in ActionType}

# ========= State Containers =========


class ModelState:
    def __init__(self) -> None:
        self.init_started: bool = False
        self.available: bool = False
        self.init_error: Optional[str] = None


# ========== Moderation JSON Schema ==========
moderation_schema = {
    "type": "object",
    "properties": {
        "channel_id": {"type": "string"},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "action": {"type": "string", "enum": ["delete", "warn", "timeout", "kick", "ban", "null"]},
                    "reason": {"type": "string"},
                    "message_ids": {"type": "array", "items": {"type": "string"}},
                    "timeout_duration": {"type": ["integer", "null"]},
                    "ban_duration": {"type": ["integer", "null"]}
                },
                "required": ["user_id", "action", "reason", "message_ids", "timeout_duration", "ban_duration"],
                "additionalProperties": False
            }
        }
    },
    "required": ["channel_id", "actions"],
    "additionalProperties": False
}

class ModerationProcessor:
    """Encapsulates the end-to-end AI moderation workflow."""

    def __init__(self) -> None:
        self._llm: Optional[LLM] = None
        self._sampling_params: Optional[SamplingParams] = None
        self._base_system_prompt: Optional[str] = None
        self.state = ModelState()
        self._init_lock = asyncio.Lock()
        self._warmup_completed: bool = False

    # ======== Model Initialization ========
    async def init_model(self, model: Optional[str] = None) -> Tuple[Optional[LLM], Optional[SamplingParams], Optional[str]]:
        async with self._init_lock:
            if self.state.available and self._llm is not None and self._sampling_params is not None:
                return self._llm, self._sampling_params, self._base_system_prompt

            if self.state.init_started and not self.state.available and self.state.init_error:
                return self._llm, self._sampling_params, self._base_system_prompt

            self.state.init_started = True

            base_configuration = cfg.app_config.reload()
            if not base_configuration:
                logger.error("[AI MODEL] Configuration is empty; cannot initialize AI model.")
                self.state.init_error = "missing configuration"
                self.state.available = False
                return None, None, None

            self._base_system_prompt = cfg.app_config.system_prompt_template
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
                return None, None, self._base_system_prompt

            if not model_identifier:
                logger.error("[AI MODEL] No model identifier provided.")
                self.state.available = False
                self.state.init_error = "missing model id"
                return None, None, self._base_system_prompt

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

                self._llm = LLM(
                    model=model_identifier,
                    dtype=dtype,
                    gpu_memory_utilization=gpu_mem_util,
                    max_model_len=max_model_length,
                    tensor_parallel_size=tp,
                )

                self._sampling_params = SamplingParams(
                    temperature=temperature,
                    max_tokens=max_new_tokens,
                    top_p=top_p,
                    top_k=top_k,
                    repetition_penalty=repetition_penalty,
                    presence_penalty=presence_penalty,
                    frequency_penalty=frequency_penalty,
                    guided_decoding=GuidedDecodingParams(json=moderation_schema),
                )

                self.state.available = True
                self.state.init_error = None
                logger.info("[AI MODEL] vLLM initialized successfully.")
                return self._llm, self._sampling_params, self._base_system_prompt

            except Exception as e:
                self.state.available = False
                self.state.init_error = f"Initialization failed: {e}"
                logger.error(f"[AI MODEL] Failed to initialize vLLM model: {e}", exc_info=True)
                return None, None, self._base_system_prompt

    async def get_model(self) -> Tuple[Optional[LLM], Optional[SamplingParams], Optional[str]]:
        if self._llm is None and not self.state.init_started:
            await self.init_model()
        return self._llm, self._sampling_params, self._base_system_prompt

    async def is_model_available(self) -> bool:
        return self.state.available

    async def get_model_init_error(self) -> Optional[str]:
        return self.state.init_error

    async def get_system_prompt(self, server_rules: str = "") -> str:
        await self.get_model()
        template = self._base_system_prompt or cfg.app_config.system_prompt_template
        return cfg.app_config.format_system_prompt(server_rules, template_override=template)

    # ======== Inference Helpers ========
    async def _messages_to_prompt(self, messages: List[Dict[str, Any]]) -> str:
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

    def _sync_generate(self, prompts: List[str]) -> List[str]:
        if self._llm is None or self._sampling_params is None:
            raise RuntimeError("Model not initialized")

        outputs = self._llm.generate(prompts, self._sampling_params)
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

        prompt = await self._messages_to_prompt(messages)

        try:
            results = await asyncio.to_thread(self._sync_generate, [prompt])
            return results[0] if results else "null: no response"
        except Exception as e:
            logger.error(f"Inference error: {e}", exc_info=True)
            return f"null: inference error"

    async def start_batch_worker(self) -> None:

        async def warmup(self) -> None:
            if self._warmup_completed:
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

            

    # ======== Parsing Utilities ========
    async def parse_action(self, assistant_response: str) -> tuple[ActionType, str]:
        cls = ActionType
        try:
            s = assistant_response.strip()
            if s.startswith('```'):
                s = '\n'.join([ln for ln in s.splitlines() if not ln.strip().startswith('```')])
            first_brace = min([i for i in [s.find('{'), s.find('[')] if i != -1], default=-1)
            last_brace = max(s.rfind('}'), s.rfind(']'))
            if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                s = s[first_brace:last_brace + 1]
            parsed = json.loads(s)
            if isinstance(parsed, dict):
                action_value = str(parsed.get('action', 'null')).lower()
                reason = str(parsed.get('reason', 'Automated moderation action'))
                if action_value in VALID_ACTION_VALUES:
                    return cls(action_value), reason
                return cls('null'), "unknown action type"
        except Exception as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            return cls('null'), "invalid JSON response"
        return cls('null'), "no action found"

    async def parse_batch_actions(self, assistant_response: str, channel_id: int) -> List[Dict[str, Any]]:
        try:
            s = assistant_response.strip()
            if s.startswith('```'):
                s = '\n'.join([ln for ln in s.splitlines() if not ln.strip().startswith('```')])
            first_brace = min([i for i in [s.find('{'), s.find('[')] if i != -1], default=-1)
            last_brace = max(s.rfind('}'), s.rfind(']'))
            if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                s = s[first_brace:last_brace + 1]
            parsed = json.loads(s)
            actions = parsed.get('actions', [])
            validated = []
            for a in actions:
                if not isinstance(a, dict):
                    continue
                user_id = str(a.get('user_id', '')).strip()
                action_value = str(a.get('action', 'null')).lower()
                if not user_id or action_value not in VALID_ACTION_VALUES:
                    continue

                reason = str(a.get('reason', 'Automated moderation action'))

                raw_message_ids = a.get('message_ids') or []
                if isinstance(raw_message_ids, list):
                    message_ids = [str(mid) for mid in raw_message_ids if str(mid).strip()]
                else:
                    message_ids = []

                timeout_duration = a.get('timeout_duration')
                if timeout_duration is not None:
                    try:
                        timeout_duration = int(timeout_duration)
                    except (TypeError, ValueError):
                        timeout_duration = None

                ban_duration = a.get('ban_duration')
                if ban_duration is not None:
                    try:
                        ban_duration = int(ban_duration)
                    except (TypeError, ValueError):
                        ban_duration = None

                validated.append(
                    {
                        'user_id': user_id,
                        'action': action_value,
                        'reason': reason,
                        'message_ids': message_ids,
                        'timeout_duration': timeout_duration,
                        'ban_duration': ban_duration,
                    }
                )
            return validated
        except Exception as e:
            logger.error(f"Error parsing batch actions: {e}")
            return []

    # ======== Public Moderation Entrypoints ========
    async def get_batch_moderation_actions(
        self,
        channel_id: int,
        messages: List[Dict[str, Any]],
        server_rules: str = "",
    ) -> List[Dict[str, Any]]:
        system_prompt = await self.get_system_prompt(server_rules)
        system_msg = {"role": "system", "content": system_prompt}
        payload = {"channel_id": str(channel_id), "messages": messages}
        user_msg = {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}
        resp = await self.submit_inference([system_msg, user_msg])

        # Parse whatever the model returned (may be sparse) and then ensure we have
        # exactly one action for every input message. If the model omitted an
        # action for a message, insert the no-op action 'null'.
        parsed_actions = await self.parse_batch_actions(resp, channel_id)

        # Build quick lookup maps from message_id -> action and user_id -> action
        msgid_map: Dict[str, Dict[str, Any]] = {}
        userid_map: Dict[str, Dict[str, Any]] = {}
        for a in parsed_actions:
            # normalize fields
            u = str(a.get("user_id", "")).strip()
            mids = a.get("message_ids") or []
            if isinstance(mids, list) and mids:
                for mid in mids:
                    mid_s = str(mid)
                    if mid_s:
                        msgid_map[mid_s] = a
            elif u:
                # fallback map by user id (first seen wins)
                userid_map.setdefault(u, a)

        final_actions: List[Dict[str, Any]] = []
        for msg in messages:
            mid = str(msg.get("message_id") or "")
            uid = str(msg.get("user_id") or "")

            chosen: Optional[Dict[str, Any]] = None
            if mid and mid in msgid_map:
                chosen = msgid_map[mid]
            elif uid and uid in userid_map:
                chosen = userid_map[uid]

            if chosen is None:
                # Default no-op action for this message
                chosen = {
                    "user_id": uid or str(msg.get("user_id", "")),
                    "action": "null",
                    "reason": "no action",
                    "message_ids": [mid] if mid else [],
                    "timeout_duration": None,
                    "ban_duration": None,
                }

            # Ensure message_ids includes the current message id if available
            mids = chosen.get("message_ids") or []
            if mid and mid not in mids:
                mids = list(mids) + [mid]
                chosen["message_ids"] = mids

            final_actions.append(chosen)

        return final_actions

    async def get_appropriate_action(
        self,
        history: List[Dict[str, Any]],
        user_id: int,
        *,
        current_message: Optional[str] = None,
        server_rules: str = "",
        channel_id: Optional[int | str] = None,
        username: Optional[str] = None,
        message_timestamp: Optional[str] = None,
    ) -> tuple[ActionType, str]:
        message_to_assess = current_message or (history[-1].get("content", "") if history else "")

        if not history and not message_to_assess.strip():
            return ActionType.NULL, "empty history"

        if not message_to_assess.strip():
            return ActionType.NULL, "empty message"

        system_prompt = await self.get_system_prompt(server_rules)
        system_msg = {"role": "system", "content": system_prompt}

        now_iso = message_timestamp or time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        payload_messages = list(history)
        payload_messages.append(
            {
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
        return await self.parse_action(assistant_response)
    
    def get_model_state(self) -> ModelState:
        return self.state


moderation_processor = ModerationProcessor()
MODEL_STATE = moderation_processor.state