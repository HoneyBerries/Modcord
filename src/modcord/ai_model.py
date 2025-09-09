import re
import sys
import asyncio
import os
from . import config_loader as cfg
from .actions import ActionType
from .logger import get_logger

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
def init_ai_model(model=None, tokenizer_param=None) -> tuple | None:
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
    config = cfg.load_config()
    BASE_SYSTEM_PROMPT = config.get("system_prompt", "")
    ai_cfg = config.get("ai_settings", {}) if isinstance(config, dict) else {}
    is_ai_enabled = bool(ai_cfg.get("enabled", False))
    is_allow_gpu = ai_cfg.get("allow_gpu", False)
    model_id = ai_cfg.get("model_id", "meta-llama/Llama-3.2-3B-Instruct")
    use_quant = ai_cfg.get("use_4bit", True)

    if model is None and tokenizer_param is None:
        if not is_ai_enabled:
            logger.info("[AI MODEL] AI disabled by configuration")
            return None

        # Lazy import heavy dependencies
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM

        has_cuda = torch.cuda.is_available()
        
        # Check if is_allow_gpu is set but no CUDA device is available
        if is_allow_gpu and not has_cuda:
            logger.critical("AI model loading requested with ai_settings." \
            "\nallow_gpu=true but no CUDA device is available. Set ai_settings." \
            "\nallow_gpu=false in config.yml to allow CPU loading (not recommended)."
            "\n\nWe will load the model on your CPU, but performance will suck.")


        # Configure 4-bit quantization for efficient GPU memory usage if CUDA is available
        bnb_config = None
        if has_cuda and use_quant:
            try:
                logger.info("[AI MODEL] Enabling 4-bit quantization for model loading")
                from transformers.utils.quantization_config import BitsAndBytesConfig
                bnb_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype=torch.bfloat16
                )
            except Exception as e:
                logger.warning(f"[AI MODEL] Could not enable 4-bit quantization: {e}. Falling back to non-quantized.")

        # Load the quantized model and tokenizer
        load_kwargs = {
            "device_map": "cuda" if has_cuda else "cpu",
            "trust_remote_code": True,
        }
        if bnb_config is not None:
            load_kwargs["quantization_config"] = bnb_config

        # Warn about missing HF token (many models require it)
        if not (os.getenv("HUGGING_FACE_HUB_TOKEN") or os.getenv("HF_TOKEN")):
            logger.warning("[AI MODEL] No Hugging Face token detected (HUGGING_FACE_HUB_TOKEN/HF_TOKEN). If the model is gated, loading will fail.")

        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            **load_kwargs,
        ).eval()  # Set to inference mode (disables dropout)

        tokenizer_local: AutoTokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)

        logger.info(f"[AI MODEL] Model loaded on {model.device}")
        return model, tokenizer_local, BASE_SYSTEM_PROMPT

    else:
        return model, tokenizer_param, BASE_SYSTEM_PROMPT

# ==============================
# Global model initialization (singleton)
# ==============================
model, tokenizer, BASE_SYSTEM_PROMPT = (None, None, None)
# Availability and diagnostics flags
MODEL_INIT_STARTED = False
MODEL_AVAILABLE = False
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
                model = tokenizer = BASE_SYSTEM_PROMPT = None
            else:
                model, tokenizer, BASE_SYSTEM_PROMPT = init_result
            MODEL_AVAILABLE = model is not None and tokenizer is not None
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
    Worker that processes inference requests in batches every ~5 seconds.
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
                results = run_inference_batch(batch_messages)
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

def run_inference_batch(batch_messages: list[list[dict]]) -> list[str]:
    """
    Process multiple inference requests in a single batch.
    
    Args:
        batch_messages: List of message lists (one per request)
        
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

        # Lazy import torch only when we actually have a model
        import torch
        # Prepare input_ids for each conversation in the batch
        input_ids_list = []
        prompt_lengths = []
        
        for messages in batch_messages:     
            ids = tokenizer.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                return_tensors="pt"
            )
            input_ids_list.append(ids)
            prompt_lengths.append(ids.shape[1])

        # Concatenate for batch processing
        input_ids = torch.cat(input_ids_list, dim=0).to(model.device)
        attention_mask = torch.ones_like(input_ids).to(model.device)
        
        logger.info(f"[BATCH] Processing batch with input shape: {input_ids.shape}")
        
        # Generate responses for all prompts
        with torch.no_grad():
            outputs = model.generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                max_new_tokens=128,
                temperature=0.01,
                top_p=0.9,
                repetition_penalty=1.1,
                do_sample=True,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
        
        # Decode each response
        responses = []
        for i, output in enumerate(outputs):
            # Extract only the new tokens (skip the original prompt)
            new_tokens = output[prompt_lengths[i]:]
            response = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
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
        _ = get_model()
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
    Parses the AI model's response to extract the moderation action and reason.
    Supports actions: delete, warn, timeout, kick, ban, null.
    Supports both formats: "action: reason" and "action: <action_type> reason: <reason>"
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

    # Pattern 1: Check for "action: <action_type> reason: <reason>" format
    action_pattern = r'action:\s*(delete|warn|timeout|kick|ban|null)(?:.*?reason:\s*(.+?))?'
    match = re.search(action_pattern, assistant_response.lower(), re.DOTALL)
    
    if match:
        action_str = match.group(1).strip().lower()
        reason = match.group(2).strip() if match.group(2) else "Automated moderation action"

        # Convert string to ActionType enum using the canonical class
        try:
            action = cls(action_str)
        except Exception:
            logger.warning(f"[AI MODEL] Unknown action type: '{action_str}'")
            return cls('null'), "unknown action type"

        # Remove redundant '<action>:' prefix from reason if present
        try:
            action_prefixes = [at.value for at in cls]
        except Exception:
            action_prefixes = [at.value for at in ActionType]
        for prefix in action_prefixes:
            if reason.lower().startswith(f"{prefix}:"):
                reason = reason[len(prefix) + 1 :].strip()
                logger.info(f"Stripped redundant action prefix '{prefix}:' from reason in AI response.")
                break

        if getattr(action, 'value', str(action)) == 'null':
            return cls('null'), "no action required or needed..."
        return action, reason

    # Pattern 2: Check for simple "<action>: <reason>" format (e.g., "ban: User was spamming")
    simple_action_pattern = r'^(delete|warn|timeout|kick|ban|null):\s*(.+)'
    simple_match = re.match(simple_action_pattern, assistant_response.strip(), re.IGNORECASE)
    if simple_match:
        action_str = simple_match.group(1).strip().lower()
        reason = simple_match.group(2).strip()
        
        try:
            action = cls(action_str)
            if getattr(action, 'value', str(action)) == 'null':
                return cls('null'), "no action needed"
            return action, reason
        except Exception:
            logger.warning(f"[AI MODEL] Unknown action type: '{action_str}'")
            return cls('null'), "unknown action type"

    # Pattern 3: Check for just the action name with no colon
    simple_pattern = r"^(delete|warn|timeout|kick|ban|null)$"
    simple_match = re.match(simple_pattern, assistant_response.strip(), re.IGNORECASE)
    if simple_match:
        action_str = simple_match.group(1).lower()
        try:
            action = cls(action_str)
            if getattr(action, 'value', str(action)) == 'null':
                return cls('null'), "no action needed"
            logger.warning(f"[AI MODEL] Invalid response format: '{assistant_response}'")
            return action, "AI response incomplete"
        except Exception:
            logger.warning(f"[AI MODEL] Unknown action type: '{action_str}'")
            return cls('null'), "unknown action type"


    # If no patterns matched, return null action with error reason
    logger.warning(f"[AI MODEL] Invalid response format: '{assistant_response}'")
    return cls('null'), "invalid AI response format"


# ==============================
# Main Moderation Action Function
async def get_appropriate_action(current_message: str, history: list[dict[str, str]], username: str, server_rules: str = "") -> tuple[ActionType, str]:
    """
    Determines the appropriate moderation action for a user's message based on chat history.

    Formats the input, runs AI inference using the batch system, and parses the response to output a moderation action.

    Args:
        current_message (str): The latest message from the user.
        history (list[dict[str, str]]): List of previous chat messages (each as a dict).
        username (str): The username of the sender.
        server_rules (str): The server rules to use for moderation context.

    Returns:
        tuple[ActionType, str]: Moderation action type and reason, or an error/null action.
    """
    logger.debug(f"Received message: '{current_message}' from user: '{username}'")
    logger.debug(f"Chat history: {history}")

    if not current_message or not current_message.strip():
        logger.info("[AI MODEL] Empty input message. Returning null.")
        return ActionType.NULL, "empty message"

    # Prepare system message with rules prompt (using dynamic rules)
    system_prompt = get_system_prompt(server_rules)
    system_msg = {"role": "system", "content": system_prompt}

    # Format user message with username context
    user_text = f"User {username} says: {current_message}" if username else current_message
    user_msg = {"role": "user", "content": user_text}

    # Format up to 48 most recent valid history messages
    formatted_history = []
    if history:
        for msg in reversed(history[-48:]):
            content = msg.get("content", "")
            if not isinstance(content, str) or not content.strip():
                continue
            if msg.get("username"):
                content = f"User {msg['username']} says: {content}"
            formatted_history.insert(0, {
                "role": msg.get("role", "user"),
                "content": content
            })

    # Compose messages for prompt: system, history, user
    messages = [system_msg] + formatted_history + [user_msg]
    logger.debug(f"Final messages for prompt: {messages}")

    # Submit to batch processing queue instead of direct inference
    assistant_response = await submit_inference(messages)
    return parse_action(assistant_response)