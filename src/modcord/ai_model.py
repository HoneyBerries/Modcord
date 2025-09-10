import re
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
async def get_appropriate_action(
    current_message: str,
    history: list[dict[str, str]],
    user_id: int,
    server_rules: str = ""
) -> tuple[ActionType, str]:
    """
    Determines the appropriate moderation action for a user's message based on chat history.

    Formats the input, runs AI inference using the batch system, and parses the response to output a moderation action.

    Args:
        current_message (str): The latest message from the user.
        history (list[dict[str, str]]): List of previous chat messages (each as a dict). Maps to {"role": str, "user_id": int, "content": str}.
        user_id (int): The Discord user ID of the sender.
        server_rules (str, optional): The server rules to use for moderation context. Defaults to "".

    Returns:
        tuple[ActionType, str]: Moderation action type and reason, or an error/null action.
    """
    logger.debug(f"Received message: '{current_message}' from user: '{user_id}'")
    logger.debug(f"Chat history: {history}")

    if not current_message or not current_message.strip():
        logger.info("[AI MODEL] Empty input message. Returning null.")
        return ActionType.NULL, "empty message"

    # Prepare system message with rules prompt (using dynamic rules)
    system_prompt = get_system_prompt(server_rules)
    system_msg = {"role": "system", "content": system_prompt}

    # Format user message with user ID context
    user_text = f"User {user_id} says: {current_message}" if user_id else current_message
    user_msg = {"role": "user", "content": user_text}

    # Format the history messages
    formatted_history = []
    if history:
        for msg in reversed(history):
            content = msg.get("content", "")
            if not isinstance(content, str) or content.strip() == "":
                continue

            if msg.get("user_id"):
                content = f"User {msg['user_id']} says: {content}"
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