"""
Fully async, self-contained vLLM-backed AI model module for moderation.
Includes model initialization, inference, warmup, and JSON parsing.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import List, Dict, Any, Optional, Tuple

import torch
from vllm import LLM, SamplingParams
from vllm.sampling_params import GuidedDecodingParams

import modcord.config_loader as cfg
from modcord.actions import ActionType
from modcord.logger import get_logger

logger = get_logger("ai_model")

# ========= Globals & State =========
llm: Optional[LLM] = None
sampling_params: Optional[SamplingParams] = None
BASE_SYSTEM_PROMPT: Optional[str] = None

class ModelState:
    def __init__(self) -> None:
        self.init_started: bool = False
        self.available: bool = False
        self.init_error: Optional[str] = None

MODEL_STATE = ModelState()

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

# ========== Model Initialization ==========
async def init_ai_model(model: Optional[str] = None) -> Tuple[Optional[LLM], Optional[SamplingParams], Optional[str]]:
    global llm, sampling_params, BASE_SYSTEM_PROMPT, MODEL_STATE

    if MODEL_STATE.init_started:
        return llm, sampling_params, BASE_SYSTEM_PROMPT

    MODEL_STATE.init_started = True

    # Load config
    try:
        base_configuration = cfg.load_config()
    except Exception as e:
        logger.error(f"[AI MODEL] Failed to load config: {e}", exc_info=True)
        MODEL_STATE.init_error = f"config load error: {e}"
        MODEL_STATE.available = False
        return None, None, None

    BASE_SYSTEM_PROMPT = base_configuration.get("system_prompt", "")
    ai_configuration = base_configuration.get("ai_settings", {})
    is_ai_enabled = bool(ai_configuration.get("enabled", False))
    is_gpu_allowed = ai_configuration.get("allow_gpu", False)
    vram_percentage = ai_configuration.get("vram_percentage", 0.5)
    model_identifier = model or ai_configuration.get("model_id")
    
    # Load AI model knobs from config
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

    
    logger.info(f"[AI MODEL] Using configuration knobs")
    logger.debug(f"temperature={temperature}, max_new_tokens={max_new_tokens}, dtype={dtype}, top_p={top_p}, top_k={top_k}, repetition_penalty={repetition_penalty}, presence_penalty={presence_penalty}, frequency_penalty={frequency_penalty}")

    if not is_ai_enabled:
        logger.info("[AI MODEL] AI disabled in configuration.")
        MODEL_STATE.available = False
        MODEL_STATE.init_error = "AI disabled in config"
        return None, None, BASE_SYSTEM_PROMPT

    if not model_identifier:
        logger.error("[AI MODEL] No model identifier provided.")
        MODEL_STATE.available = False
        MODEL_STATE.init_error = "missing model id"
        return None, None, BASE_SYSTEM_PROMPT

    cuda_available = torch.cuda.is_available()
    tp: int = torch.cuda.device_count() if cuda_available else 0

    if is_gpu_allowed and not cuda_available:
        logger.warning("[AI MODEL] GPU allowed but CUDA not available. Using CPU.")

    try:
        gpu_mem_util = vram_percentage if is_gpu_allowed and cuda_available else 0.0
        logger.info(f"[AI MODEL] Loading vLLM model '{model_identifier}' (dtype={dtype}, tp={tp}, gpu_mem={gpu_mem_util})")
        logger.info(f"[AI MODEL] Config: max_model_len={max_model_length}, temperature={temperature}, top_p={top_p}")
        
        llm = LLM(
            model=model_identifier,
            dtype=dtype,
            gpu_memory_utilization=gpu_mem_util,
            max_model_len=max_model_length,
            tensor_parallel_size=tp
        )

        sampling_params = SamplingParams(
            temperature=temperature,
            max_tokens=max_new_tokens,
            top_p=top_p,
            top_k=top_k,
            repetition_penalty=repetition_penalty,
            presence_penalty=presence_penalty,
            frequency_penalty=frequency_penalty,
            guided_decoding=GuidedDecodingParams(json=moderation_schema)
        )

        MODEL_STATE.available = True
        MODEL_STATE.init_error = None
        logger.info("[AI MODEL] vLLM initialized successfully.")
        return llm, sampling_params, BASE_SYSTEM_PROMPT

    except Exception as e:
        MODEL_STATE.available = False
        MODEL_STATE.init_error = f"Initialization failed: {e}"
        logger.error(f"[AI MODEL] Failed to initialize vLLM model: {e}", exc_info=True)
        return None, None, BASE_SYSTEM_PROMPT


async def get_model() -> Tuple[Optional[LLM], Optional[SamplingParams], Optional[str]]:
    global llm, sampling_params
    if llm is None and not MODEL_STATE.init_started:
        await init_ai_model()
    return llm, sampling_params, BASE_SYSTEM_PROMPT

async def is_model_available() -> bool:
    return MODEL_STATE.available

async def get_model_init_error() -> Optional[str]:
    return MODEL_STATE.init_error

async def get_system_prompt(server_rules: str = "") -> str:
    _, _, prompt = await get_model()
    base = BASE_SYSTEM_PROMPT or ""
    try:
        return base.format(SERVER_RULES=server_rules)
    except Exception:
        return f"{base}\n\nServer rules:\n{server_rules}"


# ========== Inference Helpers ==========
async def _messages_to_prompt(messages: List[Dict[str, Any]]) -> str:
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


def _sync_generate(prompts: List[str]) -> List[str]:
    global llm, sampling_params
    if llm is None or sampling_params is None:
        raise RuntimeError("Model not initialized")

    outputs = llm.generate(prompts, sampling_params)
    results = []
    for out in outputs:
        results.append(out.outputs[0].text.strip() if out.outputs else "")
    return results


async def submit_inference(messages: List[Dict[str, Any]]) -> str:
    if MODEL_STATE.init_started and not MODEL_STATE.available:
        reason = MODEL_STATE.init_error or "AI model unavailable"
        logger.debug(f"Short-circuiting inference; {reason}")
        return f"null: {reason}"

    _, _, _ = await get_model()
    prompt = await _messages_to_prompt(messages)

    try:
        results = await asyncio.to_thread(_sync_generate, [prompt])
        return results[0] if results else "null: no response"
    except Exception as e:
        logger.error(f"Inference error: {e}", exc_info=True)
        return f"null: inference error"


async def start_batch_worker():
    if not MODEL_STATE.init_started:
        await init_ai_model()
    try:
        asyncio.create_task(_warmup_model())
    except RuntimeError:
        logger.debug("start_batch_worker called outside event loop; skipping warmup task.")


async def _warmup_model():
    logger.info("Warming up model...")
    _, _, _ = await get_model()
    try:
        small_prompt = "[SYSTEM]\nWarmup check. Return a short JSON: {\"channel_id\":\"warmup\",\"actions\":[]}"
        out = await asyncio.to_thread(_sync_generate, [small_prompt])
        logger.info(f"Warmup complete (len={len(out[0])})")
    except Exception as e:
        logger.error(f"Warmup failed: {e}", exc_info=True)



# ========== Parsing Utilities ==========
async def parse_action(assistant_response: str) -> tuple[ActionType, str]:
    cls = ActionType
    try:
        s = assistant_response.strip()
        if s.startswith('```'):
            s = '\n'.join([ln for ln in s.splitlines() if not ln.strip().startswith('```')])
        first_brace = min([i for i in [s.find('{'), s.find('[')] if i != -1], default=-1)
        last_brace = max(s.rfind('}'), s.rfind(']'))
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            s = s[first_brace:last_brace+1]
        parsed = json.loads(s)
        if isinstance(parsed, dict):
            action_type = str(parsed.get('action', 'null')).lower()
            reason = str(parsed.get('reason', 'Automated moderation action'))
            return cls(action_type), reason
    except Exception as e:
        logger.warning(f"Failed to parse JSON response: {e}")
        return cls('null'), "invalid JSON response"
    return cls('null'), "no action found"


async def parse_batch_actions(assistant_response: str, channel_id: int) -> List[Dict[str, Any]]:
    try:
        s = assistant_response.strip()
        if s.startswith('```'):
            s = '\n'.join([ln for ln in s.splitlines() if not ln.strip().startswith('```')])
        first_brace = min([i for i in [s.find('{'), s.find('[')] if i != -1], default=-1)
        last_brace = max(s.rfind('}'), s.rfind(']'))
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            s = s[first_brace:last_brace+1]
        parsed = json.loads(s)
        actions = parsed.get('actions', [])
        validated = []
        for a in actions:
            if not isinstance(a, dict):
                continue
            validated.append({
                'user_id': str(a.get('user_id', '')),
                'action': str(a.get('action', 'null')).lower(),
                'reason': str(a.get('reason', 'Automated moderation action')),
                'delete_count': int(a.get('delete_count', 0)),
                'timeout_duration': a.get('timeout_duration'),
                'ban_duration': a.get('ban_duration')
            })
        return validated
    except Exception as e:
        logger.error(f"Error parsing batch actions: {e}")
        return []



# ========== Public Moderation Entrypoints ==========
async def get_batch_moderation_actions(channel_id: int, messages: List[Dict[str, Any]], server_rules: str = "") -> List[Dict[str, Any]]:
    system_prompt = await get_system_prompt(server_rules)
    system_msg = {"role": "system", "content": system_prompt}
    payload = {"channel_id": str(channel_id), "messages": messages}
    user_msg = {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}
    resp = await submit_inference([system_msg, user_msg])
    return await parse_batch_actions(resp, channel_id)


async def get_appropriate_action(history: List[Dict[str, Any]], user_id: int, server_rules: str = "", *, channel_id: Optional[int | str] = None, username: Optional[str] = None, message_timestamp: Optional[str] = None) -> tuple[ActionType, str]:
    if not history:
        return ActionType.NULL, "empty history"

    current_message = history[-1].get("content", "")
    if not current_message.strip():
        return ActionType.NULL, "empty message"

    system_prompt = await get_system_prompt(server_rules)
    system_msg = {"role": "system", "content": system_prompt}

    now_iso = message_timestamp or time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    payload = {"channel_id": str(channel_id) if channel_id else "unknown", "messages": history + [{"user_id": str(user_id), "username": username or f"user_{user_id}", "timestamp": now_iso, "content": current_message}]}
    user_msg = {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}

    assistant_response = await submit_inference([system_msg, user_msg])
    return await parse_action(assistant_response)