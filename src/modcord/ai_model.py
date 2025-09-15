# ai_model.py
"""
vLLM-backed AI model module for moderation.

Replaces previous HF/transformers usage with vLLM.LLM for dynamic batching and
guided decoding (JSON schema enforcement).
"""
from __future__ import annotations

import asyncio
import json
import sys
import os
import time
from typing import List, Dict, Any, Optional, Tuple

import torch

from modcord import config_loader as cfg
from modcord.actions import ActionType
from modcord.logger import get_logger

# vLLM imports
from vllm import LLM, SamplingParams
from vllm.sampling_params import GuidedDecodingParams

logger = get_logger("ai_model")

# ========= Globals & State =========
llm: Optional[LLM] = None
sampling_params: Optional[SamplingParams] = None
BASE_SYSTEM_PROMPT: str | None = None

MODEL_INIT_STARTED = False
MODEL_AVAILABLE = False
MODEL_INIT_ERROR: Optional[str] = None

# ========== Moderation JSON Schema (strict) ==========
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
                    "action": {
                        "type": "string",
                        "enum": ["delete", "warn", "timeout", "kick", "ban", "null"]
                    },
                    "reason": {"type": "string"},
                    "delete_count": {"type": "integer"},
                    "timeout_duration": {"type": ["integer", "null"]},
                    "ban_duration": {"type": ["integer", "null"]},
                },
                "required": [
                    "user_id", "action", "reason",
                    "delete_count", "timeout_duration", "ban_duration"
                ],
                "additionalProperties": False,
            }
        }
    },
    "required": ["channel_id", "actions"],
    "additionalProperties": False,
}

# ========== Model Initialization ==========
def init_ai_model(model: Optional[str] = None) -> Tuple[Optional[LLM], Optional[SamplingParams], Optional[str]]:
    """
    Initialize the vLLM model and sampling parameters.

    Returns (llm_instance, sampling_params, base_system_prompt)
    """
    global llm, sampling_params, BASE_SYSTEM_PROMPT, MODEL_AVAILABLE, MODEL_INIT_ERROR, MODEL_INIT_STARTED

    MODEL_INIT_STARTED = True

    # Load configuration
    try:
        base_configuration = cfg.load_config()
    except Exception as e:
        logger.error(f"[AI MODEL] Failed to load config: {e}", exc_info=True)
        MODEL_INIT_ERROR = f"config load error: {e}"
        MODEL_AVAILABLE = False
        return None, None, None

    BASE_SYSTEM_PROMPT = base_configuration.get("system_prompt", "")
    ai_configuration = base_configuration.get("ai_settings", {}) if isinstance(base_configuration, dict) else {}
    is_ai_enabled = bool(ai_configuration.get("enabled", False))
    is_gpu_allowed = ai_configuration.get("allow_gpu", False)
    model_identifier = model or ai_configuration.get("model_id") or os.getenv("AI_MODEL_ID")
    # We don't replicate the HF 4-bit flow here; vLLM handles model runtime.
    # Make sure a model id exists and ai is enabled
    if not is_ai_enabled:
        logger.info("[AI MODEL] AI disabled by configuration (ai_settings.enabled is false).")
        MODEL_AVAILABLE = False
        MODEL_INIT_ERROR = "ai disabled in config"
        return None, None, BASE_SYSTEM_PROMPT

    if not (isinstance(model_identifier, str) and model_identifier.strip()):
        logger.error("[AI MODEL] No model identifier provided in config or env (AI_MODEL_ID)")
        MODEL_AVAILABLE = False
        MODEL_INIT_ERROR = "missing model id"
        return None, None, BASE_SYSTEM_PROMPT

    # Prepare dtype / device options
    cuda_available = torch.cuda.is_available()
    if is_gpu_allowed and not cuda_available:
        logger.warning("[AI MODEL] ai_settings.allow_gpu=true but no CUDA available. Will run on CPU (slow).")

    dtype = "bfloat16"
    tp = torch.cuda.device_count() if cuda_available else 1

    try:
        logger.info(f"[AI MODEL] Loading vLLM model '{model_identifier}' (dtype={dtype}, tp={tp})")
        llm = LLM(
            model=model_identifier,
            dtype=dtype,
            gpu_memory_utilization=0.8,
            max_model_len=8192,
            tensor_parallel_size=tp,
        )

        sampling_params = SamplingParams(
            temperature=0.0,
            max_tokens=2048,
            top_p=0.95,
            repetition_penalty=1.05,
            guided_decoding=GuidedDecodingParams(
            json=moderation_schema
            )
        )

        MODEL_AVAILABLE = True
        MODEL_INIT_ERROR = None
        logger.info("[AI MODEL] vLLM initialized successfully.")
        return llm, sampling_params, BASE_SYSTEM_PROMPT

    except Exception as e:
        MODEL_AVAILABLE = False
        MODEL_INIT_ERROR = f"Initialization failed: {e}"
        logger.error(f"[AI MODEL] Failed to initialize vLLM model: {e}", exc_info=True)
        return None, None, BASE_SYSTEM_PROMPT


def get_model() -> Tuple[Optional[LLM], Optional[SamplingParams], Optional[str]]:
    """
    Singleton accessor for model & sampling params. Initializes on first call.
    """
    global llm, sampling_params, BASE_SYSTEM_PROMPT, MODEL_INIT_STARTED, MODEL_AVAILABLE

    if llm is None and not MODEL_INIT_STARTED:
        init_ai_model()

    return llm, sampling_params, BASE_SYSTEM_PROMPT


def is_model_available() -> bool:
    return bool(MODEL_AVAILABLE)


def get_model_init_error() -> Optional[str]:
    return MODEL_INIT_ERROR


def get_system_prompt(server_rules: str = "") -> str:
    """
    Return formatted system prompt (inserts SERVER_RULES into base prompt).
    """
    _, _, prompt = get_model()
    base = BASE_SYSTEM_PROMPT or ""
    try:
        return base.format(SERVER_RULES=server_rules)
    except Exception:
        # Fallback to simple concatenation if formatting fails
        return f"{base}\n\nServer rules:\n{server_rules}"


# ========== Inference Helpers ==========
def _messages_to_prompt(messages: List[Dict[str, Any]]) -> str:
    """
    Convert chat-style messages list (dicts with 'role' & 'content') to a single prompt string.
    We try to preserve ordering and label roles clearly.
    """
    parts: List[str] = []
    for m in messages:
        role = (m.get("role") or "user").lower()
        content = str(m.get("content") or "")
        if role == "system":
            parts.append(f"[SYSTEM]\n{content.strip()}")
        elif role == "assistant":
            parts.append(f"[ASSISTANT]\n{content.strip()}")
        else:
            # user or other roles
            parts.append(f"[USER]\n{content.strip()}")
    return "\n\n".join(parts).strip()


def _sync_generate(prompts: List[str]) -> List[str]:
    """
    Synchronous wrapper around llm.generate. Returns list of string outputs mapped to prompts.
    """
    global llm, sampling_params
    if llm is None or sampling_params is None:
        raise RuntimeError("Model not initialized")

    outputs = llm.generate(prompts, sampling_params)
    results: List[str] = []
    for out in outputs:
        if not out.outputs:
            results.append("")
        else:
            # take the first completion
            results.append(out.outputs[0].text.strip())
    return results


async def submit_inference(messages: List[Dict[str, Any]]) -> str:
    """
    Async wrapper used by existing code. Accepts 'messages' (list of dicts with 'role' and 'content'),
    builds a single prompt string, runs vLLM generation in a thread, and returns the assistant text.
    """
    global MODEL_AVAILABLE
    # Fast-path if model unavailable
    if MODEL_INIT_STARTED and not MODEL_AVAILABLE:
        reason = get_model_init_error() or "AI model unavailable"
        logger.debug(f"[AI] Short-circuiting inference; {reason}")
        return f"null: {reason}"

    llm_instance, _, _ = get_model()
    if llm_instance is None:
        logger.warning("[AI] submit_inference called but model not initialized yet.")
        return "null: model not initialized"

    prompt = _messages_to_prompt(messages)

    try:
        # Run blocking generation off the event loop
        results = await asyncio.to_thread(_sync_generate, [prompt])
        return results[0] if results else "null: no response"
    except Exception as e:
        logger.error(f"[AI] Inference error: {e}", exc_info=True)
        return f"null: inference error"


def start_batch_worker():
    """
    Kept for compatibility with older code (events.py calls this).
    We don't start a manual worker queue — vLLM batches dynamically — but we ensure
    the model is initialized and kick off a warmup task.
    """
    global MODEL_INIT_STARTED
    if not MODEL_INIT_STARTED:
        # initialize model (non-blocking)
        try:
            # try to initialize synchronously here to surfacing errors early
            init_ai_model()
        except Exception as e:
            logger.error(f"[AI] Error initializing model in start_batch_worker: {e}", exc_info=True)

    # Try to warmup in background
    try:
        asyncio.create_task(_warmup_model())
    except RuntimeError:
        # Not running inside event loop; ignore warmup
        logger.debug("[AI] start_batch_worker called outside event loop; skipping warmup task.")


async def _warmup_model():
    """Perform a lightweight warmup query to ensure model loads weights early."""
    logger.info("[AI] Warming up model...")
    llm_instance, _, _ = get_model()
    if not llm_instance:
        logger.error("[AI] Warmup aborted: model not available")
        return
    try:
        # run a tiny prompt to check generation path
        small_prompt = "[SYSTEM]\nWarmup check. Return a short JSON: {\"channel_id\":\"warmup\",\"actions\":[]}"
        out = await asyncio.to_thread(_sync_generate, [small_prompt])
        logger.info(f"[AI] Warmup complete (len={len(out[0])})")
    except Exception as e:
        logger.error(f"[AI] Warmup failed: {e}", exc_info=True)


# ========== Parsing Utilities ==========
def parse_action(assistant_response: str) -> tuple[ActionType, str]:
    """
    Parse the AI response for a single-action flow (keeps parity with your original code).
    Returns (ActionType, reason)
    """
    # Helper: find canonical ActionType class (tests may import via different name)
    def _get_canonical_action_cls():
        candidates = [
            'src.actions',
            'actions',
            'modcord.actions',
            'src.modcord.actions',
        ]
        for name in candidates:
            mod = sys.modules.get(name)
            if mod and hasattr(mod, 'ActionType'):
                return getattr(mod, 'ActionType')
        return ActionType

    cls = _get_canonical_action_cls()

    def _extract_from_dict(d: dict) -> tuple[ActionType, str]:
        if isinstance(d.get('action'), (str,)):
            a = str(d['action']).strip()
            reason = str(d.get('reason', 'Automated moderation action')).strip()
            try:
                action_obj = cls(a.lower())
            except Exception:
                logger.warning(f"[AI MODEL] Unknown action type: '{a}'")
                return cls('null'), "unknown action type"
            if getattr(action_obj, 'value', str(action_obj)) == 'null':
                return cls('null'), reason or "no action needed"
            return action_obj, reason

        mod = d.get('moderation')
        if isinstance(mod, dict) and isinstance(mod.get('action'), (str,)):
            return _extract_from_dict(mod)

        items = d.get('actions')
        if isinstance(items, list):
            for item in reversed(items):
                if isinstance(item, dict) and isinstance(item.get('action'), (str,)):
                    action_obj, reason = _extract_from_dict(item)
                    if getattr(action_obj, 'value', str(action_obj)) != 'null':
                        return action_obj, reason
            return cls('null'), "no action needed"

        return cls('null'), "no action found"

    try:
        if isinstance(assistant_response, str):
            s = assistant_response.strip()
            if s.startswith('```'):
                lines = [ln for ln in s.splitlines() if not ln.strip().startswith('```')]
                s = "\n".join(lines).strip()

            first_brace = min([i for i in [s.find('{'), s.find('[')] if i != -1], default=-1)
            last_brace = max(s.rfind('}'), s.rfind(']'))
            if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                s = s[first_brace:last_brace+1]

            parsed = json.loads(s)

            if isinstance(parsed, dict):
                extracted = _extract_from_dict(parsed)
                if extracted:
                    return extracted
            elif isinstance(parsed, list):
                for item in reversed(parsed):
                    if isinstance(item, dict):
                        extracted = _extract_from_dict(item)
                        if extracted and getattr(extracted[0], 'value', str(extracted[0])) != 'null':
                            return extracted
                return cls('null'), "no action needed"
    except Exception as e:
        logger.warning(f"[AI MODEL] Failed to parse JSON response: {e}")
        return cls('null'), "invalid JSON response"

    logger.warning(f"[AI MODEL] No actionable item found in JSON response: '{assistant_response}'")
    return cls('null'), "no action found"


def parse_batch_actions(assistant_response: str, channel_id: int) -> List[Dict[str, Any]]:
    """
    Parse the AI response for the batch flow (expected strict JSON with 'actions' array).
    Returns a list of validated action dicts (same shape your events.py expects).
    """
    logger.debug(f"Parsing batch response for channel {channel_id}: {assistant_response}")

    try:
        response = assistant_response.strip()
        if response.startswith('```'):
            lines = [ln for ln in response.splitlines() if not ln.strip().startswith('```')]
            response = "\n".join(lines).strip()

        first_brace = min([i for i in [response.find('{'), response.find('[')] if i != -1], default=-1)
        last_brace = max(response.rfind('}'), response.rfind(']'))
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            response = response[first_brace:last_brace+1]

        parsed = json.loads(response)

        if not isinstance(parsed, dict):
            logger.warning(f"Expected dict in batch response for channel {channel_id}, got {type(parsed)}")
            return []

        actions = parsed.get("actions", [])
        if not isinstance(actions, list):
            logger.warning(f"Expected list in actions for channel {channel_id}, got {type(actions)}")
            return []

        validated_actions: List[Dict[str, Any]] = []
        for action in actions:
            if not isinstance(action, dict):
                continue

            user_id = str(action.get("user_id", "")).strip()
            action_type = str(action.get("action", "null")).strip().lower()
            reason = str(action.get("reason", "Automated moderation action")).strip()

            valid_actions = ["null", "delete", "warn", "timeout", "kick", "ban"]
            if action_type not in valid_actions:
                logger.warning(f"Invalid action type '{action_type}' for user {user_id}, defaulting to null")
                action_type = "null"

            delete_count = int(action.get("delete_count", 0))
            timeout_duration = action.get("timeout_duration")
            ban_duration = action.get("ban_duration")

            if timeout_duration is not None:
                try:
                    timeout_duration = int(timeout_duration)
                except (ValueError, TypeError):
                    timeout_duration = None

            if ban_duration is not None:
                try:
                    ban_duration = int(ban_duration)
                except (ValueError, TypeError):
                    ban_duration = None

            validated_action = {
                "user_id": user_id,
                "action": action_type,
                "reason": reason,
                "delete_count": max(0, delete_count),
                "timeout_duration": timeout_duration,
                "ban_duration": ban_duration
            }

            if action_type != "null" and user_id:
                validated_actions.append(validated_action)
                logger.debug(f"Validated action: {validated_action}")

        logger.info(f"Parsed {len(validated_actions)} valid actions for channel {channel_id}")
        return validated_actions

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON in batch response for channel {channel_id}: {e}")
        return []
    except Exception as e:
        logger.error(f"Error parsing batch actions for channel {channel_id}: {e}", exc_info=True)
        return []


# ========== Public Moderation Entrypoints ==========
async def get_batch_moderation_actions(
    channel_id: int,
    messages: List[Dict[str, Any]],
    server_rules: str = ""
) -> List[Dict[str, Any]]:
    """
    Process a batch of messages from a single channel and return moderation actions.

    This builds the JSON payload expected by the system prompt and uses submit_inference.
    """
    logger.info(f"Processing batch for channel {channel_id} with {len(messages)} messages")

    if not messages:
        return []

    # Prepare system prompt with server rules
    system_prompt = get_system_prompt(server_rules)
    system_msg = {"role": "system", "content": system_prompt}

    # Build the payload JSON as required by your system
    try:
        payload = {
            "channel_id": str(channel_id),
            "messages": []
        }

        for msg in messages:
            payload["messages"].append({
                "user_id": str(msg.get("user_id", "")),
                "username": str(msg.get("username", "unknown")),
                "timestamp": msg.get("timestamp") or time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                "content": str(msg.get("content", "")),
                "image_summary": msg.get("image_summary")
            })

        user_msg = {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}
        prompt_messages = [system_msg, user_msg]

        logger.debug(f"Batch payload: {payload}")

    except Exception as e:
        logger.error(f"Failed to build batch payload for channel {channel_id}: {e}", exc_info=True)
        return []

    try:
        assistant_response = await submit_inference(prompt_messages)
        return parse_batch_actions(assistant_response, channel_id)
    except Exception as e:
        logger.error(f"Error in batch inference for channel {channel_id}: {e}", exc_info=True)
        return []


async def get_appropriate_action(
    history: List[Dict[str, Any]],
    user_id: int,
    server_rules: str = "",
    *,
    channel_id: Optional[int | str] = None,
    username: Optional[str] = None,
    message_timestamp: Optional[str] = None,
) -> tuple[ActionType, str]:
    """
    Single-message flow — builds a payload with the given history and asks the model
    for a single moderation action. Returns (ActionType, reason).
    """
    logger.debug(f"Received history with {len(history)} messages from user: '{user_id}'")
    if not history:
        logger.info("[AI MODEL] Empty history. Returning null.")
        return ActionType.NULL, "empty history"

    current_message = history[-1].get("content", "") if history else ""
    if not current_message or not str(current_message).strip():
        logger.info("[AI MODEL] Empty current message. Returning null.")
        return ActionType.NULL, "empty message"

    system_prompt = get_system_prompt(server_rules)
    system_msg = {"role": "system", "content": system_prompt}

    try:
        now_iso = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        payload = {
            "channel_id": str(channel_id) if channel_id is not None else "unknown",
            "messages": []
        }

        if history:
            for msg in history:
                content = msg.get("content", "")
                if not isinstance(content, str) or content.strip() == "":
                    continue
                uid = msg.get("user_id")
                uname = msg.get("username") or (f"user_{uid}" if uid is not None else "unknown")
                ts = msg.get("timestamp") or None
                payload["messages"].append({
                    "user_id": str(uid) if uid is not None else "",
                    "username": str(uname),
                    "timestamp": ts,
                    "content": content,
                    "image_summary": msg.get("image_summary", None),
                })

        payload["messages"].append({
            "user_id": str(user_id),
            "username": username or f"user_{user_id}",
            "timestamp": message_timestamp or now_iso,
            "content": current_message,
            "image_summary": None,
        })

        user_msg = {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}
        messages = [system_msg, user_msg]
        logger.debug(f"Final JSON payload for prompt: {payload}")
    except Exception as e:
        logger.error(f"[AI MODEL] Failed to build JSON payload: {e}", exc_info=True)
        return ActionType.NULL, "payload build error"

    assistant_response = await submit_inference(messages)
    return parse_action(assistant_response)


# End of ai_model.py
