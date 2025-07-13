import logging
import re
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from transformers.utils.quantization_config import BitsAndBytesConfig
import config_loader as cfg

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
    Initializes the LLaMA AI model, tokenizer, and moderation system prompt.

    Loads configuration, server rules, and system prompt using the config loader.
    Sets up 4-bit quantized inference for efficient memory usage.
    Loads the model and tokenizer on the available GPU(s) and disables dropout for inference.

    Returns:
        model (PreTrainedModel): Quantized LLaMA model ready for inference.
        tokenizer (PreTrainedTokenizer): Tokenizer for the loaded model.
        SYSTEM_PROMPT (str): System prompt guiding moderation behavior.
    """
    # Load configuration and server rules
    config = cfg.load_config()
    SERVER_RULES = cfg.get_server_rules(config)
    SYSTEM_PROMPT = cfg.get_system_prompt(config, SERVER_RULES)

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
    logger.info(f"[AI MODEL] Model loaded on device: {model.device}")
    return model, tokenizer, SYSTEM_PROMPT

# ==============================
# Global model initialization (singleton)
# ==============================
model, tokenizer, SYSTEM_PROMPT = init_ai_model()

def run_inference(messages: list) -> str:
    """
    Runs inference on a list of chat messages and generates an AI response.

    The function formats the conversation history into the proper prompt format,
    runs inference using the loaded model, and decodes the output.

    Args:
        messages (list): List of message dicts, each containing 'role' and 'content'.

    Returns:
        str: The generated raw response string from the AI model.
             Returns error strings if inference fails.

    Raises:
        torch.cuda.OutOfMemoryError: If GPU runs out of memory during inference.
        Exception: For other errors during inference.

    Notes:
        - Uses tokenizer's chat template if available, otherwise falls back to manual prompt construction.
        - Logs key stages for debugging.
        - Configures generation parameters for quality and diversity.
    """
    try:
        # Format input using chat template if supported
        if hasattr(tokenizer, "apply_chat_template"):
            logger.info("[AI MODEL] Using tokenizer's apply_chat_template for prompt formatting.")
            inputs = tokenizer.apply_chat_template(
                messages,
                return_tensors="pt",
                max_length=6144,
                truncation=True,
                add_generation_prompt=True
            )
            logger.debug("Applied chat template to messages.")
        else:
            # Fallback to manual prompt construction
            logger.warning("[AI MODEL] Tokenizer does not support apply_chat_template, falling back to manual prompt construction.")
            prompt = "\n".join([f"{msg['role']}: {msg['content']}" for msg in messages])
            logger.debug(f"Manual prompt: {prompt}")
            inputs = tokenizer(
                prompt,
                return_tensors="pt",
                max_length=6144,
                truncation=True
            )

        # Move input tensor to model's device
        input_ids = inputs.to(model.device)
        logger.debug(f"Input IDs: {input_ids}")
        attention_mask = torch.ones_like(input_ids).to(model.device)
        logger.debug(f"Attention mask: {attention_mask}")
        prompt_length = input_ids.shape[1]
        logger.info(f"[AI MODEL] Using {prompt_length} tokens for prompt")

        # Run model inference without gradients
        with torch.no_grad():
            logger.debug("Starting model.generate()")
            output = model.generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                max_new_tokens=128,
                temperature=0.2,
                top_p=0.7,
                top_k=50,
                repetition_penalty=1.2,
                do_sample=True,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
            logger.debug(f"Model output tensor: {output}")

        # Extract generated tokens beyond the prompt
        new_tokens = output[0, prompt_length:]
        logger.debug(f"New tokens: {new_tokens}")
        assistant_response = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
        logger.debug(f"Decoded assistant response: '{assistant_response}'")
        return assistant_response

    except torch.cuda.OutOfMemoryError:
        # Handle GPU memory errors gracefully
        logger.critical("[AI MODEL] GPU ran out of memory")
        return "null: GPU memory error"
    except Exception as e:
        # Log and report other errors
        logger.error(f"[AI MODEL ERROR] {type(e).__name__}: {e}")
        return "null: AI model error"

# ==============================
# Action Parsing and Moderation Logic
def parse_action(assistant_response: str) -> str:
    """
    Parses the AI model's response to extract the moderation action and reason.

    Supports actions: warn, timeout, kick, ban, null.

    Args:
        assistant_response (str): Raw response from the AI model.

    Returns:
        str: Action and reason in the format '<action>: <reason>'.
             Returns fallback or invalid format strings if parsing fails.

    Implementation:
        - Uses regex for robust extraction of action and reason.
        - Provides fallback parsing for partial responses.
        - Logs parsing steps and warnings for debugging.
    """
    action_pattern = r"^(warn|timeout|kick|ban|null)\s*:\s*(.+?)(?:\n|$)"
    match = re.match(action_pattern, assistant_response, re.IGNORECASE | re.DOTALL)

    if match:
        action = match.group(1).lower()
        reason = match.group(2).strip().rstrip('.')
        logger.debug(f"Parsed action: {action}, reason: {reason}")
        valid_actions = {"warn", "timeout", "kick", "ban", "null"}
        if action in valid_actions:
            result = f"{action}: {reason}"
            logger.info(f"[AI ACTION] {result}")
            return result

    # Fallback: Try to extract just the action if parsing failed
    simple_pattern = r"(warn|timeout|kick|ban|null)"
    simple_match = re.search(simple_pattern, assistant_response, re.IGNORECASE)
    if simple_match:
        action = simple_match.group(1).lower()
        result = f"{action}: rule violation detected"
        logger.warning(f"[AI MODEL] Partial response recovered: {result}")
        return result

    logger.warning(f"[AI MODEL] Invalid response format: '{assistant_response}'")
    return "null: invalid AI response format"

# ==============================
# Main Moderation Action Function
async def get_appropriate_action(current_message: str, history: list[dict[str, str]], username: str) -> str:
    """
    Determines the appropriate moderation action for a user's message based on chat history.

    Formats the input, runs AI inference, and parses the response to output a moderation action.

    Args:
        current_message (str): The latest message from the user.
        history (list[dict[str, str]]): List of previous chat messages (each as a dict).
        username (str): The username of the sender.

    Returns:
        str: Moderation action and reason, or an error/null string.

    Implementation steps:
        - Logs received message and history for debugging.
        - Handles empty input gracefully.
        - Prepares system and user messages for the prompt.
        - Includes up to 20 most recent valid history messages in the prompt.
        - Runs inference and parses the action.
    """
    logger.debug(f"Received message: '{current_message}' from user: '{username}'")
    logger.debug(f"Chat history: {history}")

    if not current_message or not current_message.strip():
        logger.info("[AI MODEL] Empty input message. Returning null.")
        return "null: empty message"

    # Prepare system message with rules prompt
    system_msg = {"role": "system", "content": SYSTEM_PROMPT}

    # Format user message with username context
    user_text = f"User {username} says: {current_message}" if username else current_message
    user_msg = {"role": "user", "content": user_text}

    # Format up to 20 most recent valid history messages
    formatted_history = []
    if history:
        for msg in reversed(history[-20:]):
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

    # Run inference and parse moderation action
    assistant_response = run_inference(messages)
    return parse_action(assistant_response)