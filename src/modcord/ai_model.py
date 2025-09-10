import json
import sys
import asyncio
import os
import torch
import time
from . import config_loader as cfg
from .actions import ActionType
from .logger import get_logger
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

# ==============================
# Logging configuration
# ==============================
logger = get_logger("ai_model")

# Ensure this module is reachable via multiple import paths (tests may patch 'modcord.ai_model')
_this_module = sys.modules[__name__]
for _alias in [
    'ai_model',
    'modcord.ai_model',
]:
    if _alias not in sys.modules:
        sys.modules[_alias] = _this_module

# ==============================
# Model, Tokenizer, and System Prompt Initialization
def init_ai_model(model=None, tokenizer_parameter=None) -> tuple | None:
    """
    Initializes the LLaMA AI model, tokenizer, and loads base configuration.

    Loads base configuration and system prompt template from config.yml.
    Sets up 4-bit quantized inference for efficient memory usage.
    Loads the model and tokenizer on the available GPU(s) and disables dropout for inference.

    Note: Server rules are now loaded dynamically per guild and passed at inference time.

    Returns:
        model (PreTrainedModel): Quantized LLaMA model ready for inference.
        tokenizer (PreTrainedTokenizer): Tokenizer for the loaded model.
        BASE_SYSTEM_PROMPT (str): Base system prompt template (with {SERVER_RULES} placeholder).
    """
    # Load base configuration (without dynamic rules)
    base_configuration = cfg.load_config()
    BASE_SYSTEM_PROMPT = base_configuration.get("system_prompt", "")
    ai_configuration = base_configuration.get("ai_settings", {}) if isinstance(base_configuration, dict) else {}
    is_artificial_intelligence_enabled = bool(ai_configuration.get("enabled", False))
    is_gpu_usage_allowed = ai_configuration.get("allow_gpu", False)
    model_identifier = ai_configuration.get("model_id")
    use_4bit_quantization = ai_configuration.get("use_4bit")

    # Only proceed if all required parameters are provided
    can_proceed_with_initialization = all([isinstance(model_identifier, str) and model_identifier.strip(), isinstance(use_4bit_quantization, bool), is_artificial_intelligence_enabled])
    
    if can_proceed_with_initialization:
        if not is_artificial_intelligence_enabled:
            logger.info("[AI MODEL] AI disabled by configuration")
            return None
       

        cuda_available = torch.cuda.is_available()
        
        # Check if is_gpu_usage_allowed is set but no CUDA device is available
        if is_gpu_usage_allowed and not cuda_available:
            logger.critical("AI model loading requested with ai_settings." \
            "\nallow_gpu=true but no CUDA device is available. Set ai_settings." \
            "\nallow_gpu=false in config.yml to allow CPU loading (not recommended)."
            "\n\nWe will load the model on your CPU, but performance will suck.")


        # Configure 4-bit quantization for efficient GPU memory usage if CUDA is available
        quantization_config = None
        if cuda_available and use_4bit_quantization:
            try:
                logger.info("[AI MODEL] Enabling 4-bit quantization for model loading")
                from transformers.utils.quantization_config import BitsAndBytesConfig
                quantization_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype=torch.bfloat16
                )
            except Exception as e:
                logger.warning(f"[AI MODEL] Could not enable 4-bit quantization: {e}. Falling back to non-quantized.")

        # Load the quantized model and tokenizer
        model_loading_kwargs = {
            "device_map": "cuda" if cuda_available else "cpu",
            "trust_remote_code": True,
        }
        if quantization_config is not None:
            model_loading_kwargs["quantization_config"] = quantization_config

        # Warn about missing HF token (many models require it)
        if not (os.getenv("HUGGING_FACE_HUB_TOKEN") or os.getenv("HF_TOKEN")):
            logger.warning("[AI MODEL] No Hugging Face token detected (HUGGING_FACE_HUB_TOKEN/HF_TOKEN). If the model is gated, loading will fail.")

        model = AutoModelForCausalLM.from_pretrained(
            model_identifier, # type: ignore
            **model_loading_kwargs,
        ).eval()  # Set to inference mode (disables dropout)      

        local_tokenizer: AutoTokenizer = AutoTokenizer.from_pretrained(model_identifier, trust_remote_code=True)

        logger.info(f"[AI MODEL] Model loaded on {model.device}")
        return torch.compile(model), local_tokenizer, BASE_SYSTEM_PROMPT

    else:
        return model, tokenizer_parameter, BASE_SYSTEM_PROMPT




# ==============================
# Global model initialization (singleton)
# ==============================

model, tokenizer, BASE_SYSTEM_PROMPT = (None, None, None)

# Availability and diagnostics flags
MODEL_INIT_STARTED = MODEL_AVAILABLE = False
MODEL_INIT_ERROR: str | None = None


def get_model() -> tuple:
    """
    Initializes and returns the AI model, tokenizer, and base system prompt.
    Uses a singleton pattern to ensure the model is loaded only once.
    """
    global model, tokenizer, BASE_SYSTEM_PROMPT, MODEL_INIT_STARTED, MODEL_AVAILABLE, MODEL_INIT_ERROR

    if model is None and not MODEL_INIT_STARTED:
        MODEL_INIT_STARTED = True

        try:
            init_result = init_ai_model()
            if init_result is None:
                # Model initialization failed or AI disabled
                model = tokenizer = BASE_SYSTEM_PROMPT = None
            else:
                model, tokenizer, BASE_SYSTEM_PROMPT = init_result
            MODEL_AVAILABLE = (model is not None) and (tokenizer is not None)

            # Log the result
            if MODEL_AVAILABLE:
                logger.info("[AI MODEL] Model initialized successfully.")
            else:
                MODEL_INIT_ERROR = "Model initializer returned None"
                logger.error("[AI MODEL] Model initialization returned None; AI unavailable.")

        except Exception as e:
            MODEL_AVAILABLE = False
            MODEL_INIT_ERROR = f"Initialization failed: {e}"
            logger.error(f"[AI MODEL] Failed to initialize model: {e}", exc_info=True)
    return model, tokenizer, BASE_SYSTEM_PROMPT


def is_model_available() -> bool:
    return MODEL_AVAILABLE

def get_model_init_error() -> str | None:
    return MODEL_INIT_ERROR

def get_system_prompt(server_rules: str = "") -> str:
    """
    Generate the system prompt with dynamic server rules.
    
    Args:
        server_rules (str): The server rules to inject into the prompt.
        
    Returns:
        str: The formatted system prompt with rules.
    """
    _, _, prompt = get_model()
    return prompt.format(SERVER_RULES=server_rules)


# ==============================
# Batch Processing Queue System
# ==============================
inference_queue = asyncio.Queue()
_worker_task = None

async def inference_worker():
    """
    Worker that processes inference requests in batches every 5 seconds.
    Collects requests for up to 5 seconds, then processes them all at once.
    """
    while True:
        batch = []
        try:
            # Wait for at least one item (blocking)
            first_item = await inference_queue.get()
            batch.append(first_item)
            
            # Collect more items for up to 5 seconds
            end_time = asyncio.get_event_loop().time() + 5.0
            while asyncio.get_event_loop().time() < end_time:
                try:
                    # Try to get more items with a short timeout
                    item = await asyncio.wait_for(inference_queue.get(), timeout=0.1)
                    batch.append(item)
                except asyncio.TimeoutError:
                    continue
                
            # Process the batch
            batch_messages: list = [item[0] for item in batch]
            batch_futures: list[asyncio.Future] = [item[1] for item in batch]

            logger.info(f"[BATCH] Processing batch of {len(batch)} requests")
            
            try:
                # Offload the blocking inference work to a thread so the asyncio
                # event loop remains responsive (slash commands, other tasks).
                results = await asyncio.to_thread(run_inference_batch, batch_messages)
                for result, future in zip(results, batch_futures):
                    if not future.cancelled():
                        future.set_result(result)

            except Exception as e:
                logger.error(f"[BATCH] Error processing batch: {e}", exc_info=True)
                for future in batch_futures:
                    if not future.cancelled():
                        future.set_result("null: batch processing error")
            
            # Mark all tasks as done
            for _ in batch:
                inference_queue.task_done()
                
        except Exception as e:
            logger.error(f"[BATCH] Worker error: {e}", exc_info=True)
            if batch:
                for _, future in batch:
                    if not future.cancelled():
                        future.set_result("null: worker error")
                for _ in batch:
                    inference_queue.task_done()


# The core of this whole project :)
def run_inference_batch(batch_messages: list[list[dict]]) -> list[str]:
    """
    Process multiple inference requests in a single batch.
    
    Args:
        batch_messages: List of message lists (one per request). For each element in the list, there is a list of dicts for each message in the conversation.
        
    Returns:
        List of response strings (one per request)
    """
    try:
        # Ensure model is (attempted) initialized
        model, tokenizer, _ = get_model()
        if not (model and tokenizer):
            reason = get_model_init_error() or "AI model unavailable"
            logger.warning(f"[BATCH] Skipping batch; {reason}")
            return ["null: ai unavailable"] * len(batch_messages)
        
        tokenizer.padding_side = 'left'  # Ensure padding side is left for decoder-only models
        
        # Ensure pad token is set for generation
        if tokenizer.pad_token_id is None:

            # Fallback to eos token if pad is unset
            if tokenizer.eos_token_id is not None:
                tokenizer.pad_token = tokenizer.eos_token
                tokenizer.pad_token_id = tokenizer.eos_token_id
                logger.debug("[BATCH] Pad token was unset; using eos token as pad token.")

            else:
                tokenizer.pad_token_id = 0

        # Build chat prompts as strings (not tokenized) for proper batch tokenization
        prompts: list[str] = []
        for messages in batch_messages:
            prompt_str = tokenizer.apply_chat_template(
                messages,
                tokenize=False,              # get string prompts
                add_generation_prompt=True,
            )
            prompts.append(prompt_str)

        # Tokenize the batch of prompts with padding
        batch = tokenizer(
            prompts,
            padding=True,
            truncation=True,
            return_tensors="pt",
        )

        # Extract tensors
        input_ids = batch["input_ids"]
        attention_mask = batch["attention_mask"]

        # Compute per-sample prompt lengths (non-padded token count)
        prompt_lengths = attention_mask.sum(dim=1).tolist()

        logger.info(f"[BATCH] Processing batch with input shape: {tuple(input_ids.shape)}")

        # Log batch stats (debug)
        batch_size = input_ids.size(0)
        logger.debug(
            f"[BATCH] Stats - size: {batch_size}, "
            f"min_len: {int(min(prompt_lengths)) if prompt_lengths else 0}, "
            f"max_len: {int(max(prompt_lengths)) if prompt_lengths else 0}, "
            f"avg_len: {float(sum(prompt_lengths)/batch_size) if batch_size else 0:.2f}"
        )

        # Move tensors to model device
        device = model.device
        input_ids = input_ids.to(device)
        attention_mask = attention_mask.to(device)

        # Time the inference
        start_time = time.time()

        # Generate responses for all prompts
        with torch.no_grad():
            outputs = model.generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                max_new_tokens=128,
                temperature=0.1,
                top_p=0.9,
                repetition_penalty=1.1,
                do_sample=True,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )

        inference_time = time.time() - start_time
        logger.debug(f"[BATCH] Inference time: {inference_time:.3f} seconds")

        # Decode each response (slice off the original prompt part)
        responses: list[str] = []
        for i in range(outputs.size(0)):
            new_tokens = outputs[i, int(prompt_lengths[i]):]
            # Ensure tokens on CPU for decoding
            response = tokenizer.decode(new_tokens.detach().cpu().tolist(), skip_special_tokens=True).strip()
            responses.append(response)

        logger.info(f"[BATCH] Generated {len(responses)} responses")
        return responses

    except Exception as e:
        # Prefer clear, generic failure to avoid noisy logs spamming
        logger.error(f"[BATCH] Error in batch processing: {e}", exc_info=True)
        return ["null: batch processing error"] * len(batch_messages)



async def submit_inference(messages: list[dict]) -> str:
    """
    Submit an inference request to the batch processing queue.
    
    Args:
        messages: List of message dicts for the conversation
        
    Returns:
        The AI response string
    """
    global _worker_task

    # Fast-path: if model is known to be unavailable, short-circuit
    if MODEL_INIT_STARTED and not MODEL_AVAILABLE:
        reason = get_model_init_error() or "AI model unavailable"
        logger.debug(f"[AI] Short-circuiting inference; {reason}")
        return f"null: {reason}"
    
    # Start the worker if it's not running
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(inference_worker())
    
    # Create a future for this request
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    
    # Add to queue
    await inference_queue.put((messages, future))
    
    # Wait for result
    return await future

def start_batch_worker():
    """Start the batch processing worker. Call this when the bot starts."""
    global _worker_task
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(inference_worker())
        logger.info("[BATCH] Started inference worker")
        # Kick off a warmup in the background so we fail fast at startup if needed
        try:
            asyncio.create_task(_warmup_model())
        except RuntimeError:
            # Not in an event loop yet; skip warmup silently
            pass

async def _warmup_model():
    """Attempt to initialize the model early to surface failures at startup."""
    try:
        logger.info("[AI] Warming up model...")
        
        # Load AI model now
        get_model()
        if is_model_available():
            logger.info("[AI] Model warmup complete.")
        else:
            logger.error(f"[AI] Model warmup failed: {get_model_init_error()}")
    except Exception as e:
        logger.error(f"[AI] Model warmup error: {e}", exc_info=True)

# ==============================
# Action Parsing and Moderation Logic
def parse_action(assistant_response: str) -> tuple[ActionType, str]:
    """
        Parse the AI response and extract a single moderation action and reason.

        JSON-ONLY per config.yml system (no regex fallback):
        - {"action": "ban", "reason": "..."}
        - {"moderation": {"action": "warn", "reason": "..."}}
        - {"actions": [{"user_id": "...", "action": "delete", "reason": "..."}, ...]}
            In a list, select the last non-null actionable item; if none, return null.
    """
    # Helper: find a canonical ActionType class from loaded modules (tests may import via different paths)
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
        # fallback to the local imported ActionType
        return ActionType

    cls = _get_canonical_action_cls()

    # Try JSON first
    def _coerce_action(val: str) -> tuple:
        try:
            action_obj = cls(str(val).strip().lower())
            if getattr(action_obj, 'value', str(action_obj)) == 'null':
                return cls('null'), "no action needed"
            return action_obj, "Automated moderation action"
        except Exception:
            logger.warning(f"[AI MODEL] Unknown action type: '{val}'")
            return cls('null'), "unknown action type"

    def _extract_from_dict(d: dict) -> tuple[ActionType, str] | None:
        # common top-level keys
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

        # nested under 'moderation'
        mod = d.get('moderation')
        if isinstance(mod, dict) and isinstance(mod.get('action'), (str,)):
            return _extract_from_dict(mod)

        # list under 'actions'
        items = d.get('actions')
        if isinstance(items, list):
            for item in reversed(items):
                if isinstance(item, dict) and isinstance(item.get('action'), (str,)):
                    action_obj, reason = _extract_from_dict(item)
                    if getattr(action_obj, 'value', str(action_obj)) != 'null':
                        return action_obj, reason
            # if we got here, either no items or all null
            return cls('null'), "no action needed"

        return None

    try:
        if isinstance(assistant_response, str):
            # Strip code fences if model wrapped JSON
            s = assistant_response.strip()
            if s.startswith('```'):
                # remove the first fence line and trailing fence
                lines = [ln for ln in s.splitlines() if not ln.strip().startswith('```')]
                s = "\n".join(lines).strip()

            # Trim to the first JSON-like block if there's extra chatter
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
                # Find the last actionable item in the list
                for item in reversed(parsed):
                    if isinstance(item, dict):
                        extracted = _extract_from_dict(item)
                        if extracted and getattr(extracted[0], 'value', str(extracted[0])) != 'null':
                            return extracted
                return cls('null'), "no action needed"
    except Exception as e:
        logger.warning(f"[AI MODEL] Failed to parse JSON response: {e}")
        return cls('null'), "invalid JSON response"

    # If JSON is parsed but no actionable item is found
    logger.warning(f"[AI MODEL] No actionable item found in JSON response: '{assistant_response}'")
    return cls('null'), "no action found"


# ==============================
# Batch Moderation Action Function (New Design)
async def get_batch_moderation_actions(
    channel_id: int,
    messages: list[dict],
    server_rules: str = ""
) -> list[dict]:
    """
    Process a batch of messages from a single channel and return multiple moderation actions.
    
    This implements the new 15-second batching design where all messages from a channel
    are processed together in a single AI inference call.
    
    Args:
        channel_id (int): The Discord channel ID where the messages were posted
        messages (list[dict]): List of message data dicts with keys:
            - user_id (int): Discord user ID  
            - username (str): Username for readability
            - content (str): Message content
            - timestamp (str): ISO 8601 timestamp
            - image_summary (str|None): Text summary if image was posted
        server_rules (str): Server rules for moderation context
        
    Returns:
        list[dict]: List of action dicts with keys:
            - user_id (str): Who the action applies to
            - action (str): One of "null", "delete", "warn", "timeout", "kick", "ban"
            - reason (str): Why the action was taken
            - delete_count (int): Number of messages to delete
            - timeout_duration (int|None): Seconds for timeout
            - ban_duration (int|None): Seconds for ban (0 for permanent)
    """
    logger.info(f"Processing batch for channel {channel_id} with {len(messages)} messages")
    
    if not messages:
        return []
    
    # Prepare system message with rules prompt
    system_prompt = get_system_prompt(server_rules)
    system_msg = {"role": "system", "content": system_prompt}
    
    # Build the JSON payload for the new batching format
    try:
        payload = {
            "channel_id": str(channel_id),
            "messages": []
        }
        
        # Convert messages to the required format
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
        logger.error(f"Failed to build batch payload for channel {channel_id}: {e}")
        return []
    
    # Submit to batch processing queue
    try:
        assistant_response = await submit_inference(prompt_messages)
        return parse_batch_actions(assistant_response, channel_id)
    except Exception as e:
        logger.error(f"Error in batch inference for channel {channel_id}: {e}")
        return []


def parse_batch_actions(assistant_response: str, channel_id: int) -> list[dict]:
    """
    Parse the AI response for batch processing and extract multiple moderation actions.
    
    Expected JSON format:
    {
      "channel_id": "...",
      "actions": [
        {
          "user_id": "...",
          "action": "warn|delete|timeout|kick|ban|null",
          "reason": "...",
          "delete_count": 0,
          "timeout_duration": null,
          "ban_duration": null
        }
      ]
    }
    
    Args:
        assistant_response (str): Raw AI response string
        channel_id (int): Channel ID for logging context
        
    Returns:
        list[dict]: List of validated action dictionaries
    """
    logger.debug(f"Parsing batch response for channel {channel_id}: {assistant_response}")
    
    try:
        # Clean up response if wrapped in code fences
        response = assistant_response.strip()
        if response.startswith('```'):
            lines = [ln for ln in response.splitlines() if not ln.strip().startswith('```')]
            response = "\n".join(lines).strip()
        
        # Extract JSON content
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
        
        # Validate and normalize each action
        validated_actions = []
        for action in actions:
            if not isinstance(action, dict):
                continue
                
            # Extract and validate required fields
            user_id = str(action.get("user_id", "")).strip()
            action_type = str(action.get("action", "null")).strip().lower()
            reason = str(action.get("reason", "Automated moderation action")).strip()
            
            # Validate action type
            valid_actions = ["null", "delete", "warn", "timeout", "kick", "ban"]
            if action_type not in valid_actions:
                logger.warning(f"Invalid action type '{action_type}' for user {user_id}, defaulting to null")
                action_type = "null"
            
            # Extract optional fields with defaults
            delete_count = int(action.get("delete_count", 0))
            timeout_duration = action.get("timeout_duration")
            ban_duration = action.get("ban_duration")
            
            # Convert timeout/ban durations to int or None
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
                "delete_count": max(0, delete_count),  # Ensure non-negative
                "timeout_duration": timeout_duration,
                "ban_duration": ban_duration
            }
            
            # Only include non-null actions
            if action_type != "null" and user_id:
                validated_actions.append(validated_action)
                logger.debug(f"Validated action: {validated_action}")
        
        logger.info(f"Parsed {len(validated_actions)} valid actions for channel {channel_id}")
        return validated_actions
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON in batch response for channel {channel_id}: {e}")
        return []
    except Exception as e:
        logger.error(f"Error parsing batch actions for channel {channel_id}: {e}")
        return []


# ==============================
# Main Moderation Action Function
async def get_appropriate_action(
    history: list[dict[str, str]],
    user_id: int,
    server_rules: str = "",
    *,
    channel_id: int | str | None = None,
    username: str | None = None,
    message_timestamp: str | None = None,
) -> tuple[ActionType, str]:
    """
    Determines the appropriate moderation action for a user's message based on chat history.
    
    The current message is expected to be the last item in the history list.

    Formats the input, runs AI inference using the batch system, and parses the response to output a moderation action.

    Args:
        history (list[dict[str, str]]): List of chat messages including current message (each as a dict). 
                                      Maps to {"role": str, "user_id": int, "content": str}.
        user_id (int): The Discord user ID of the sender.
        server_rules (str, optional): The server rules to use for moderation context. Defaults to "".
        channel_id: Optional channel ID for context
        username: Optional username for context  
        message_timestamp: Optional timestamp for current message

    Returns:
        tuple[ActionType, str]: Moderation action type and reason, or an error/null action.
    """
    logger.debug(f"Received history with {len(history)} messages from user: '{user_id}'")
    logger.debug(f"Chat history: {history}")

    if not history:
        logger.info("[AI MODEL] Empty history. Returning null.")
        return ActionType.NULL, "empty history"
        
    # Extract current message from history (should be the last item)
    current_message = history[-1].get("content", "") if history else ""
    if not current_message or not current_message.strip():
        logger.info("[AI MODEL] Empty current message. Returning null.")
        return ActionType.NULL, "empty message"

    # Prepare system message with rules prompt (using dynamic rules)
    system_prompt = get_system_prompt(server_rules)
    system_msg = {"role": "system", "content": system_prompt}

    # Build JSON payload for the model per new schema
    # channel_id is optional; default to "unknown" if not provided
    try:
        now_iso = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        payload = {
            "channel_id": str(channel_id) if channel_id is not None else "unknown",
            "messages": []
        }

        # Include history as prior messages if provided
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

        # Append the current message as the last entry
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
        logger.error(f"[AI MODEL] Failed to build JSON payload: {e}")
        return ActionType.NULL, "payload build error"

    # Submit to batch processing queue instead of direct inference
    assistant_response = await submit_inference(messages)
    return parse_action(assistant_response)