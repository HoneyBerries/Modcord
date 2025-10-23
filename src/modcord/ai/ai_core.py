"""Synchronous LLM core with async wrapper for non-blocking inference."""

from __future__ import annotations

import asyncio
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
    """Tracks the state of the AI model."""
    init_started: bool = False
    available: bool = False
    init_error: Optional[str] = None


class InferenceProcessor:
    """
    Synchronous LLM with async wrappers for non-blocking inference.

    Uses vLLM's synchronous LLM() class with llm.chat() for multimodal generation.
    Wraps blocking calls in asyncio.to_thread() to prevent blocking the event loop.

    Attributes:
        llm (Optional[Any]): The synchronous LLM instance.
        sampling_params (Optional[Any]): Base SamplingParams configuration.
        base_system_prompt (Optional[str]): The base system prompt template.
        state (ModelState): Tracks model state, availability, and errors.
        init_lock (asyncio.Lock): Ensures thread-safe model initialization.
    """

    def __init__(self) -> None:
        """Initialize the InferenceProcessor with default state."""
        self.llm: Optional[Any] = None
        self.sampling_params: Optional[Any] = None
        self.base_system_prompt: Optional[str] = None
        self.state = ModelState()
        self.init_lock = asyncio.Lock()

    def _set_init_error(self, msg: str) -> None:
        """Set initialization error and mark unavailable."""
        self.state.available = False
        self.state.init_error = msg

    async def init_model(self, model: Optional[str] = None) -> bool:
        """Initialize the vLLM synchronous engine.
        
        Thread-safe initialization with lock to prevent concurrent init attempts.
        Wraps blocking I/O in asyncio.to_thread() to avoid blocking event loop.

        Args:
            model: Optional model identifier override.

        Returns:
            True if initialization succeeded, False otherwise.
        """
        async with self.init_lock:
            # Already initialized
            if self.state.available and self.llm and self.sampling_params:
                return True
            
            # Previously failed - don't retry
            if self.state.init_started and self.state.init_error and not self.state.available:
                return False
            
            self.state.init_started = True
            
            # Load configuration
            base_config = cfg.app_config.reload()
            if not base_config:
                self._set_init_error("missing configuration")
                return False
            
            # Check if AI is enabled
            ai_config = cfg.app_config.ai_settings or {}
            if not ai_config.get("enabled", False):
                self._set_init_error("AI disabled in config")
                return False
            
            # Get model ID
            model_id = model or ai_config.get("model_id")
            if not model_id:
                self._set_init_error("missing model id")
                return False
            
            # Prepare sampling parameters
            self.base_system_prompt = cfg.app_config.system_prompt_template
            sampling_defaults = {
                "dtype": "auto",
                "max_new_tokens": 256,
                "max_model_length": 2048,
                "temperature": 1.0,
                "top_p": 1.0,
                "top_k": -1,
            }
            sampling_params = {**sampling_defaults, **(ai_config.get("sampling_parameters") or {})}
            vram_percentage = float(ai_config.get("vram_percentage", 0.5))
            
            # Initialize in thread pool
            result = await asyncio.to_thread(
                self._init_model_sync,
                model_id,
                sampling_params,
                vram_percentage
            )
            
            return result

    def _init_model_sync(
        self,
        model_id: str,
        sampling_parameters: Dict[str, Any],
        vram_percentage: float
    ) -> bool:
        """Synchronous model initialization (runs in thread)."""
        try:
            import torch
            from vllm import LLM, SamplingParams
        except ImportError as exc:
            self._set_init_error(f"AI libraries not available: {exc}")
            logger.error("[AI MODEL] vLLM imports failed: %s", exc)
            return False
        
        # Configure GPU usage
        cuda_available = torch.cuda.is_available()
        tensor_parallel = torch.cuda.device_count() if cuda_available else 1
        
        chosen_dtype = sampling_parameters.get("dtype", "auto")
        if not cuda_available and str(chosen_dtype).lower() in {"half", "float16", "bfloat16", "bf16"}:
            logger.info("[AI MODEL] Forcing dtype to 'float32' (GPU unavailable)")
            chosen_dtype = "float32"
        
        gpu_mem_util = vram_percentage if cuda_available else 0.0
        
        try:
            # Initialize LLM with multimodal limits
            self.llm = LLM(
                model=model_id,
                dtype=chosen_dtype,
                gpu_memory_utilization=gpu_mem_util,
                max_model_len=sampling_parameters["max_model_length"],
                tensor_parallel_size=tensor_parallel,
                trust_remote_code=True,
                limit_mm_per_prompt={"image": 8, "video": 0},
                skip_mm_profiling=True,
            )
            
            # Initialize sampling parameters
            self.sampling_params = SamplingParams(
                temperature=sampling_parameters["temperature"],
                max_tokens=sampling_parameters["max_new_tokens"],
                top_p=sampling_parameters["top_p"],
                top_k=sampling_parameters["top_k"],
            )
            
            self.state.available = True
            self.state.init_error = None
            logger.info("[AI MODEL] Model '%s' initialized successfully", model_id)
            return True
        except Exception as exc:
            self._set_init_error(f"Initialization failed: {exc}")
            logger.error("[AI MODEL] LLM initialization failed: %s", exc)
            return False

    def is_model_available(self) -> bool:
        """Check if the model is available for inference."""
        return self.state.available

    def get_model_init_error(self) -> Optional[str]:
        """Retrieve the last initialization error, if any."""
        return self.state.init_error

    def get_system_prompt(self, server_rules: str = "") -> str:
        """
        Return the system prompt with server rules injected.

        Args:
            server_rules: Server rules to inject into the <|SERVER_RULES_INJECT|> placeholder.

        Returns:
            Formatted system prompt string with rules inserted.
        """
        template = self.base_system_prompt or cfg.app_config.system_prompt_template
        template_str = str(template or "")
        rules_str = str(server_rules or "")
        
        if "<|SERVER_RULES_INJECT|>" in template_str:
            return template_str.replace("<|SERVER_RULES_INJECT|>", rules_str)
        
        if rules_str:
            return f"{template_str}\n\nServer rules:\n{rules_str}"
        return template_str

    async def generate_chat(
        self,
        messages: List[Dict[str, Any]],
        guided_decoding_grammar: Optional[str] = None
    ) -> str:
        """
        Generate text output from chat messages with optional guided decoding.
        
        Uses llm.chat() with multimodal support (text + PIL images).
        Runs in a thread to avoid blocking the event loop.

        Args:
            messages: List of message dicts with role and content (text or multimodal list).
            guided_decoding_grammar: Optional xgrammar grammar string for structured outputs.

        Returns:
            Generated output string.

        Raises:
            RuntimeError: If the model is not available.
        """
        if not self.llm or not self.sampling_params:
            reason = self.state.init_error or "AI model unavailable"
            raise RuntimeError(reason)

        logger.info("[GENERATE_CHAT] Starting generation with %d messages", len(messages))

        # Run the synchronous generation in a thread
        result = await asyncio.to_thread(
            self._generate_chat_sync,
            messages,
            guided_decoding_grammar
        )
        
        return result

    def _generate_chat_sync(
        self,
        messages: List[Dict[str, Any]],
        guided_decoding_grammar: Optional[str]
    ) -> str:
        """Synchronous chat generation (runs in thread)."""
        from vllm import SamplingParams
        
        # Create sampling params with optional guided decoding
        sampling_params = self.sampling_params
        if guided_decoding_grammar and self.sampling_params:
            from vllm.sampling_params import GuidedDecodingParams
            
            guided_params = GuidedDecodingParams(
                grammar=guided_decoding_grammar,
                disable_fallback=True,
            )
            # Create new SamplingParams with guided decoding
            sampling_params = SamplingParams(
                temperature=self.sampling_params.temperature,
                max_tokens=self.sampling_params.max_tokens,
                top_p=self.sampling_params.top_p,
                top_k=self.sampling_params.top_k,
                guided_decoding=guided_params,
            )
            logger.debug("[GENERATE_CHAT] Using guided decoding with xgrammar")

        try:
            # Use llm.chat() for multimodal generation
            if self.llm:
                outputs = self.llm.chat(messages, sampling_params=sampling_params)
                
                # Extract the final output
                if outputs and len(outputs) > 0:
                    last_output = outputs[-1] if isinstance(outputs, list) else outputs
                    if hasattr(last_output, 'outputs') and last_output.outputs:
                        result_text = last_output.outputs[0].text.strip()
                        logger.info("[GENERATE_CHAT] Generation complete: %d chars", len(result_text))
                        return result_text
            
            logger.warning("[GENERATE_CHAT] No output received")
            return ""
        except Exception as exc:
            logger.error("[GENERATE_CHAT] Error during generation: %s", exc)
            raise

    def get_model_state(self) -> ModelState:
        """Return the current model state."""
        return self.state

    async def unload_model(self) -> None:
        """
        Unload the model and clean up resources.
        
        Clears GPU memory and resets all state attributes.
        """
        async with self.init_lock:
            self.llm = None
            self.sampling_params = None
            self.state.available = False
            self.state.init_started = False
            self.state.init_error = None

        # Run cleanup in thread
        await asyncio.to_thread(self._cleanup_gpu)
        
        logger.info("[AI MODEL] Model unloaded")

    def _cleanup_gpu(self) -> None:
        """Synchronous GPU cleanup (runs in thread)."""
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
        except Exception as exc:
            logger.debug("[AI MODEL] CUDA cache cleanup failed: %s", exc)

        gc.collect()


inference_processor = InferenceProcessor()
model_state = inference_processor.state