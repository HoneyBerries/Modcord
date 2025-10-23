
"""
Synchronous LLM core with async wrappers for non-blocking, high-throughput inference.

This module manages the lifecycle and usage of a vLLM-based language model for moderation and generation tasks.
It provides:
- Thread-safe, async model initialization and unloading
- Batch inference with per-conversation guided decoding (xgrammar)
- Dynamic system prompt injection with server rules
- Resource cleanup and error tracking

All blocking operations are wrapped in asyncio.to_thread() to avoid blocking the event loop.
"""

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
    """
    Tracks the state of the AI model.

    Attributes:
        init_started (bool): Whether initialization has started.
        available (bool): Whether the model is available for inference.
        init_error (Optional[str]): Last initialization error, if any.
    """
    init_started: bool = False
    available: bool = False
    init_error: Optional[str] = None



class InferenceProcessor:
    """
    Synchronous LLM with async wrappers for non-blocking, multi-channel inference.

    - Uses vLLM's synchronous LLM() class with llm.chat() for multimodal, batch generation.
    - All blocking calls are wrapped in asyncio.to_thread() to keep the event loop responsive.
    - Supports per-conversation guided decoding (xgrammar) and dynamic system prompts.

    Attributes:
        llm (Optional[Any]): The synchronous LLM instance (vLLM).
        sampling_params (Optional[Any]): Base SamplingParams configuration.
        base_system_prompt (Optional[str]): The base system prompt template.
        state (ModelState): Tracks model state, availability, and errors.
        init_lock (asyncio.Lock): Ensures thread-safe model initialization and unloading.
    """

    def __init__(self) -> None:
        """
        Initialize the InferenceProcessor with default state and lock.
        """
        self.llm: Optional[Any] = None
        self.sampling_params: Optional[Any] = None
        self.base_system_prompt: Optional[str] = None
        self.state = ModelState()
        self.init_lock = asyncio.Lock()

    def _set_init_error(self, msg: str) -> None:
        """
        Set initialization error and mark model as unavailable.
        """
        self.state.available = False
        self.state.init_error = msg

    async def init_model(self, model: Optional[str] = None) -> bool:
        """
        Initialize the vLLM synchronous engine (thread-safe, async).

        - Loads configuration and checks if AI is enabled.
        - Prepares sampling parameters and system prompt.
        - Runs blocking model load in a thread to avoid blocking the event loop.
        - Ensures only one initialization attempt at a time.

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
        """
        Synchronous model initialization (runs in thread).

        - Imports vLLM and torch libraries.
        - Configures GPU and dtype.
        - Instantiates the LLM and sampling parameters.
        - Handles all exceptions and logs errors.

        Returns:
            True if model initialized successfully, False otherwise.
        """
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
        """
        Check if the model is available for inference.
        """
        return self.state.available

    def get_model_init_error(self) -> Optional[str]:
        """
        Retrieve the last initialization error, if any.
        """
        return self.state.init_error

    def get_system_prompt(self, server_rules: str = "") -> str:
        """
        Return the system prompt with server rules injected.

        - If the template contains <|SERVER_RULES_INJECT|>, replaces it with the provided rules.
        - Otherwise, appends rules at the end if present.

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

    async def generate_multi_chat(
        self,
        conversations: List[List[Dict[str, Any]]],
        grammar_strings: List[str]
    ) -> List[str]:
        """
        Generate text outputs from multiple conversations in a single batch call (async).

        - Uses llm.chat() with multimodal support for batch processing.
        - Each conversation can have its own guided decoding grammar (xgrammar).
        - Runs in a thread to avoid blocking the event loop.

        Args:
            conversations: List of conversation message lists.
            grammar_strings: List of xgrammar grammar strings (one per conversation).

        Returns:
            List of generated output strings (one per conversation).

        Raises:
            RuntimeError: If the model is not available.
        """
        if not self.llm or not self.sampling_params:
            reason = self.state.init_error or "AI model unavailable"
            raise RuntimeError(reason)

        logger.debug("[GENERATE_MULTI_CHAT] Starting batch generation with %d conversations", len(conversations))

        # Run the synchronous batch generation in a thread
        results = await asyncio.to_thread(
            self._generate_multi_chat_sync,
            conversations,
            grammar_strings
        )
        
        return results

    def _generate_multi_chat_sync(
        self,
        conversations: List[List[Dict[str, Any]]],
        grammar_strings: List[str]
    ) -> List[str]:
        """
        Synchronous multi-conversation batch generation (runs in thread).

        - Builds a list of SamplingParams, each with its own guided decoding grammar.
        - Calls llm.chat() for all conversations in a single batch.
        - Extracts and returns the generated text for each conversation.

        Args:
            conversations: List of conversation message lists.
            grammar_strings: List of xgrammar grammar strings (one per conversation).

        Returns:
            List of generated output strings (one per conversation).
        """
        from vllm import SamplingParams
        from vllm.sampling_params import GuidedDecodingParams
        
        # Build sampling params list (one per conversation)
        sampling_params_list = []
        for grammar_str in grammar_strings:
            if grammar_str and self.sampling_params:
                guided_params = GuidedDecodingParams(
                    grammar=grammar_str,
                    disable_fallback=True,
                )
                sp = SamplingParams(
                    temperature=self.sampling_params.temperature,
                    max_tokens=self.sampling_params.max_tokens,
                    top_p=self.sampling_params.top_p,
                    top_k=self.sampling_params.top_k,
                    guided_decoding=guided_params,
                )
            else:
                sp = self.sampling_params
            sampling_params_list.append(sp)
        
        logger.debug("[GENERATE_MULTI_CHAT] Using guided decoding for %d conversations", len(conversations))

        try:
            # Use llm.chat() with list of conversations for batch processing
            if self.llm:
                all_outputs = self.llm.chat(
                    messages=conversations,
                    sampling_params=sampling_params_list,
                    use_tqdm=False,
                )
                
                # Extract outputs for each conversation
                results = []
                for batch_output in all_outputs:
                    if hasattr(batch_output, 'outputs') and batch_output.outputs:
                        result_text = batch_output.outputs[0].text.strip()
                        results.append(result_text)
                    else:
                        logger.warning("[GENERATE_MULTI_CHAT] No output for conversation")
                        results.append("")
                
                logger.debug("[GENERATE_MULTI_CHAT] Batch generation complete: %d results", len(results))
                return results
            
            logger.warning("[GENERATE_MULTI_CHAT] No outputs received")
            return ["" for _ in conversations]
        except Exception as exc:
            logger.error("[GENERATE_MULTI_CHAT] Error during batch generation: %s", exc)
            raise

    def get_model_state(self) -> ModelState:
        """
        Return the current model state.
        """
        return self.state

    async def unload_model(self) -> None:
        """
        Unload the model and clean up resources (async).

        - Resets all state attributes and clears GPU memory.
        - Ensures thread-safe unloading with a lock.
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
        """
        Synchronous GPU cleanup (runs in thread).

        - Calls torch.cuda.empty_cache() if available.
        - Runs Python garbage collection.
        """
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