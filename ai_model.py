import logging
import re
import torch
import asyncio
from transformers import AutoTokenizer, AutoModelForCausalLM
from transformers.utils.quantization_config import BitsAndBytesConfig
import config_loader as cfg
from actions import ActionType

# ==============================
# Logging configuration
# ==============================
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)
logging.getLogger("transformers").setLevel(logging.ERROR)

# ==============================
# Model, Tokenizer, and System Prompt Initialization
def init_ai_model():
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

    model_id = "meta-llama/Llama-3.2-3B-Instruct"

    # Configure 4-bit quantization for efficient GPU memory usage
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16
    )

    # Load the quantized model and tokenizer
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        quantization_config=bnb_config,
        device_map="auto",  # Automatically assign model parts to available GPUs
        trust_remote_code=True
    ).eval()  # Set to inference mode (disables dropout)

    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    
    # Set pad token for batch processing (required for padding in batches)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        logger.info("[AI MODEL] Set pad_token to eos_token for batch processing")
    
    logger.info(f"[AI MODEL] Model loaded on device: {model.device}")
    return model, tokenizer, BASE_SYSTEM_PROMPT

# ==============================
# Global model initialization (singleton)
# ==============================
model, tokenizer, BASE_SYSTEM_PROMPT = init_ai_model()

def get_system_prompt(server_rules: str = "") -> str:
    """
    Generate the system prompt with dynamic server rules.
    
    Args:
        server_rules (str): The server rules to inject into the prompt.
        
    Returns:
        str: The formatted system prompt with rules.
    """
    return BASE_SYSTEM_PROMPT.format(SERVER_RULES=server_rules)

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
            batch_messages = [item[0] for item in batch]
            batch_futures = [item[1] for item in batch]
            
            logger.info(f"[BATCH] Processing batch of {len(batch)} requests")
            
            try:
                results = run_inference_batch(batch_messages)
                for result, future in zip(results, batch_futures):
                    if not future.cancelled():
                        future.set_result(result)
            except Exception as e:
                logger.error(f"[BATCH] Error processing batch: {e}")
                for future in batch_futures:
                    if not future.cancelled():
                        future.set_result("null: batch processing error")
            
            # Mark all tasks as done
            for _ in batch:
                inference_queue.task_done()
                
        except Exception as e:
            logger.error(f"[BATCH] Worker error: {e}")
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
        prompts = []
        
        # Format all prompts as strings
        for messages in batch_messages:
            if hasattr(tokenizer, "apply_chat_template"):
                # Get the string prompt first
                prompt = tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,  # Return string, not tokens
                    add_generation_prompt=True
                )
            else:
                prompt = "\n".join([f"{msg['role']}: {msg['content']}" for msg in messages])
            
            # Ensure prompt is a string
            if isinstance(prompt, str):
                prompts.append(prompt)
            else:
                logger.warning(f"[BATCH] Non-string prompt type: {type(prompt)}, converting to string")
                prompts.append(str(prompt))
        
        logger.info(f"[BATCH] Formatted {len(prompts)} string prompts")
        
        # Tokenize all prompts together - now all prompts are guaranteed to be strings
        inputs = tokenizer(
            prompts, 
            return_tensors="pt", 
            padding=True, 
            truncation=True, 
            max_length=6144
        )
        
        input_ids = inputs["input_ids"].to(model.device)
        attention_mask = inputs["attention_mask"].to(model.device)
        
        # Calculate original prompt lengths for each item in batch
        prompt_lengths = []
        for i in range(input_ids.shape[0]):
            # Find the actual length (excluding padding)
            prompt_length = (attention_mask[i] == 1).sum().item()
            prompt_lengths.append(prompt_length)
        
        logger.info(f"[BATCH] Processing batch with input shape: {input_ids.shape}")
        
        # Generate responses for all prompts
        with torch.no_grad():
            outputs = model.generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                max_new_tokens=256,
                temperature=0.1,
                top_p=0.7,
                top_k=50,
                repetition_penalty=1.2,
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
        
    except torch.cuda.OutOfMemoryError:
        logger.critical("[BATCH] GPU ran out of memory during batch processing")
        return ["null: GPU memory error"] * len(batch_messages)
    except Exception as e:
        logger.error(f"[BATCH] Error in batch processing: {e}")
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

# ==============================
# Action Parsing and Moderation Logic
def parse_action(assistant_response: str) -> tuple[ActionType, str]:
    """
    Parses the AI model's response to extract the moderation action and reason.
    Supports actions: delete, warn, timeout, kick, ban, null.

    Args:
        assistant_response (str): The raw response from the AI model.

    Returns:
        tuple[ActionType, str]: Action type and reason string.
    """
    action_pattern = r"^(delete|warn|timeout|kick|ban|null)\s*:\s*(.+)$"
    match = re.match(action_pattern, assistant_response.strip(), re.IGNORECASE | re.DOTALL)

    if match:
        action_str, reason = match.groups()
        action_str = action_str.strip().lower()
        reason = reason.strip()
        
        # Convert string to ActionType enum
        try:
            action = ActionType(action_str)
        except ValueError:
            logger.warning(f"[AI MODEL] Unknown action type: '{action_str}'")
            return ActionType.NULL, "unknown action type"
        
        # Fix: Remove redundant <action>: prefix from reason if present
        action_prefixes = [at.value for at in ActionType]
        for prefix in action_prefixes:
            if reason.lower().startswith(f"{prefix}:"):
                reason = reason[len(prefix)+1:].strip()
                logger.info(f"Stripped redundant action prefix '{prefix}:' from reason in AI response.")
                break
        
        # Accept 'null: no action needed' as a valid no-action response
        if action == ActionType.NULL:
            return ActionType.NULL, "no action needed"
        else:
            # Return the valid action and reason without modification
            return action, reason

    # Fallback: Try to extract just the action if parsing failed
    simple_pattern = r"^(delete|warn|timeout|kick|ban|null)$"
    simple_match = re.match(simple_pattern, assistant_response.strip(), re.IGNORECASE)
    if simple_match:
        action_str = simple_match.group(1).lower()
        try:
            action = ActionType(action_str)
            if action == ActionType.NULL:
                return ActionType.NULL, "no action needed"
            logger.warning(f"[AI MODEL] Invalid response format: '{assistant_response}'")
            return action, "AI response incomplete"
        except ValueError:
            logger.warning(f"[AI MODEL] Unknown action type: '{action_str}'")
            return ActionType.NULL, "unknown action type"

    logger.warning(f"[AI MODEL] Invalid response format: '{assistant_response}'")
    return ActionType.NULL, "invalid AI response format"

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
            # Add username context if available
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