"""Synchronous moderation model core backed by vLLM."""

from __future__ import annotations

import gc
import os
from dataclasses import dataclass
from typing import Any, List, Optional, Dict
import modcord.configuration.app_configuration as cfg
from modcord.util.logger import get_logger
logger = get_logger("ai_core")
os.environ.setdefault("TORCH_COMPILE_CACHE_DIR", "./torch_compile_cache")


@dataclass
class ModelState:
    init_started: bool = False
    available: bool = False
    init_error: Optional[str] = None


class InferenceProcessor:
    """
    Synchronous moderation model core backed by vLLM with guided decoding.

    Manages the lifecycle and inference operations of an AI model for moderation tasks.
    Uses xgrammar-based guided decoding to enforce JSON schema compliance.

    Core Responsibilities:
        - Handles initialization, configuration, and unloading of the vLLM engine
        - Loads model configuration and sampling parameters from application settings
        - Configures guided decoding with xgrammar backend for JSON schema enforcement
        - Provides methods to check model availability and retrieve initialization errors
        - Formats and returns system prompts with server rules injection
        - Generates text outputs using llm.chat() with guided decoding
        - Cleans up resources and GPU memory upon model unload

    Attributes:
        llm (Optional[Any]): The LLM instance.
        sampling_params (Optional[Any]): SamplingParams with guided decoding configuration.
        base_system_prompt (Optional[str]): The base system prompt template.
        state (ModelState): Tracks model state, availability, and errors.
    """

    def __init__(self) -> None:
        """
        Initializes the InferenceProcessor with default state.
        """
        self.llm: Optional[Any] = None
        self.sampling_params: Optional[Any] = None
        self.base_system_prompt: Optional[str] = None
        self.state = ModelState()

    def _build_dynamic_schema(self, user_ids: List[str]) -> Dict[str, Any]:
        """
        Builds a dynamic JSON schema with specific user IDs to prevent hallucination.
        
        Args:
            user_ids: List of actual user IDs from the batch
            
        Returns:
            JSON schema with user_id enum constrained to actual users
        """
        return {
            "type": "object",
            "properties": {
                "channel_id": {"type": "string"},
                "users": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "user_id": {
                                "type": "string",
                                "enum": user_ids  # Constrain to actual user IDs
                            },
                            "action": {
                                "type": "string",
                                "enum": ["null", "delete", "warn", "timeout", "kick", "ban"]
                            },
                            "reason": {"type": "string"},
                            "message_ids_to_delete": {
                                "type": "array",
                                "items": {"type": "string"}
                            },
                            "timeout_duration": {
                                "type": "integer",
                                "minimum": -1,
                                "description": "Timeout duration in minutes. Use -1 for permanent timeout, 0 for not applicable/no timeout."
                            },
                            "ban_duration": {
                                "type": "integer",
                                "minimum": -1,
                                "description": "Ban duration in minutes. Use -1 for permanent ban, 0 for not applicable/no ban."
                            }
                        },
                        "required": [
                            "user_id",
                            "action",
                            "reason",
                            "message_ids_to_delete",
                            "timeout_duration",
                            "ban_duration"
                        ],
                        "additionalProperties": False
                    }
                }
            },
            "required": ["channel_id", "users"],
            "additionalProperties": False
        }

    def init_model(self, model: Optional[str] = None) -> bool:
        """
        Initializes the vLLM engine synchronously.

        Args:
            model: Optional model identifier override.

        Returns:
            True if initialization succeeded, False otherwise.
        """
        if self.state.available and self.llm and self.sampling_params:
            return True

        if self.state.init_started and self.state.init_error and not self.state.available:
            return False

        self.state.init_started = True

        base_config = cfg.app_config.reload()
        if not base_config:
            self.base_system_prompt = None
            self.state.available = False
            self.state.init_error = "missing configuration"
            return False

        self.base_system_prompt = cfg.app_config.system_prompt_template
        ai_config = cfg.app_config.ai_settings or {}

        if not ai_config.get("enabled", False):
            self.state.available = False
            self.state.init_error = "AI disabled in config"
            return False

        model_id = model or ai_config.get("model_id")
        if not model_id:
            self.state.available = False
            self.state.init_error = "missing model id"
            return False

        sampling_defaults = {
            "dtype": "auto",
            "max_new_tokens": 256,
            "max_model_length": 2048,
            "temperature": 1.0,
            "top_p": 1.0,
            "top_k": -1,
        }
        sampling_parameters = {**sampling_defaults, **(ai_config.get("sampling_parameters") or {})}
        vram_percentage = float(ai_config.get("vram_percentage", 0.5))

        try:
            import torch
            from vllm import LLM, SamplingParams
        except ImportError as exc:
            self.state.available = False
            self.state.init_error = f"AI libraries not available: {exc}"
            logger.error("[AI MODEL] vLLM imports failed: %s", exc)
            return False

        cuda_available = torch.cuda.is_available()
        tensor_parallel = torch.cuda.device_count() if cuda_available else 1

        chosen_dtype = sampling_parameters.get("dtype", "auto")
        if not cuda_available:
            if str(chosen_dtype).lower() in {"half", "float16", "bfloat16", "bf16"}:
                logger.info(
                    "[AI MODEL] Forcing dtype to 'float32' due to GPU being unavailable"
                )
                chosen_dtype = "float32"

        gpu_mem_util = vram_percentage if cuda_available else 0.0

        try:
            # Configure multimodal limits
            limit_mm_per_prompt = {"image": 8, "video": 0}
            
            # Initialize synchronous LLM
            self.llm = LLM(
                model=model_id,
                dtype=chosen_dtype,
                gpu_memory_utilization=gpu_mem_util,
                max_model_len=sampling_parameters["max_model_length"],
                tensor_parallel_size=tensor_parallel,
                trust_remote_code=True,
                limit_mm_per_prompt=limit_mm_per_prompt,
                skip_mm_profiling=True,
            )
            
            # Create base sampling params (will be updated per request with dynamic schema)
            self.sampling_params = SamplingParams(
                temperature=sampling_parameters["temperature"],
                max_tokens=sampling_parameters["max_new_tokens"],
                top_p=sampling_parameters["top_p"],
                top_k=sampling_parameters["top_k"],
            )
            
            logger.info("[AI MODEL] Sampling params created (schema will be dynamic per request)")
        except Exception as exc:
            self.state.available = False
            self.state.init_error = f"Initialization failed: {exc}"
            logger.error("[AI MODEL] LLM initialization failed: %s", exc)
            return False

        self.state.available = True
        self.state.init_error = None
        logger.info("[AI MODEL] Model '%s' initialized", model_id)
        return True

    def get_model(self) -> bool:
        """
        Ensures the model is initialized.

        Returns:
            True if model is available, False otherwise.
        """
        if not self.state.init_started:
            return self.init_model()
        return self.state.available

    def is_model_available(self) -> bool:
        """Checks if the model is available for inference."""
        return self.state.available

    def get_model_init_error(self) -> Optional[str]:
        """Retrieves the last initialization error, if any."""
        return self.state.init_error

    def get_system_prompt(self, server_rules: str = "") -> str:
        """
        Returns the system prompt with server rules injected.

        Args:
            server_rules: Server rules to inject into the <|SERVER_RULES_INJECT|> placeholder.

        Returns:
            Formatted system prompt string with rules inserted.
        """
        self.get_model()
        template = self.base_system_prompt or cfg.app_config.system_prompt_template
        template_str = str(template or "")
        rules_str = str(server_rules or "")
        
        # Simple string replacement - supports <|SERVER_RULES_INJECT|> placeholder format
        if "<|SERVER_RULES_INJECT|>" in template_str:
            return template_str.replace("<|SERVER_RULES_INJECT|>", rules_str)
        
        # Fallback: append rules if no placeholder found
        if rules_str:
            return f"{template_str}\n\nServer rules:\n{rules_str}"
        return template_str

    def generate_chat(self, messages: List[Dict[str, Any]], user_ids: List[str], channel_id: str) -> str:
        """
        Generates text output from chat messages with guided decoding.
        
        Uses llm.chat() with dynamically generated schema based on actual user IDs
        to prevent hallucination. Images should be included as image_pil in content.

        Args:
            messages: List of message dicts with role and content (can include images).
            user_ids: List of actual user IDs from the batch to constrain schema.
            channel_id: Channel ID for the moderation batch.

        Returns:
            Generated output string (JSON constrained by dynamic schema).

        Raises:
            RuntimeError: If the model is not available or initialization failed.
        """
        if not self.llm or not self.sampling_params:
            reason = self.state.init_error or "AI model unavailable"
            raise RuntimeError(reason)

        logger.info("[GENERATE_CHAT] Starting generation with %d messages", len(messages))

        # Build dynamic schema with actual user IDs
        schema = self._build_dynamic_schema(user_ids)
        
        # Create grammar from schema
        try:
            from xgrammar.grammar import Grammar
            from vllm.sampling_params import StructuredOutputsParams
        except ImportError as exc:
            raise RuntimeError(f"xgrammar not available: {exc}")
        
        grammar_obj = Grammar.from_json_schema(schema, strict_mode=True)
        structured_output_params = StructuredOutputsParams(grammar=str(grammar_obj))
        
        # Create sampling params with structured outputs
        sampling_params = SamplingParams(
            temperature=self.sampling_params.temperature,
            max_tokens=self.sampling_params.max_tokens,
            top_p=self.sampling_params.top_p,
            top_k=self.sampling_params.top_k,
            structured_outputs=structured_output_params,
        )
        
        logger.info("[GENERATE_CHAT] Using llm.chat() with dynamic schema (user_ids=%s)", user_ids)
        
        # Use llm.chat() like test_multi_image.py
        last = None
        try:
            for out in self.llm.chat(messages, sampling_params=sampling_params):
                last = out
        except Exception as exc:
            logger.error("[GENERATE_CHAT] chat failed: %s", exc)
            raise
        
        if not last or not getattr(last, "outputs", None):
            logger.warning("[GENERATE_CHAT] no output received")
            return ""
        
        result_text = last.outputs[0].text.strip()
        logger.info("[GENERATE_CHAT] Complete: %d chars", len(result_text))
        return result_text

    def get_model_state(self) -> ModelState:
        """Returns the current model state."""
        return self.state

    def unload_model(self) -> None:
        """
        Unloads the model and cleans up resources.
        
        Clears GPU memory and resets all state attributes.
        """
        self.llm = None
        self.sampling_params = None
        self.state.available = False
        self.state.init_started = False
        self.state.init_error = None

        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
        except Exception as exc:
            logger.debug("[AI MODEL] CUDA cache cleanup failed: %s", exc)

        gc.collect()
        logger.info("[AI MODEL] Model unloaded")


inference_processor = InferenceProcessor()
model_state = inference_processor.state