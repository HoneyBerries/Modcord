"""
Synchronous LLM core with async wrappers for non-blocking, high-throughput inference.

This module manages the lifecycle and usage of a vLLM-based language model for moderation and generation tasks.

Features:
- Thread-safe, async model initialization and unloading
- Batch inference with per-conversation guided decoding (xgrammar)
- Dynamic system prompt injection with server rules and channel guidelines
- Resource cleanup and error tracking

All blocking operations are wrapped in asyncio.to_thread() to avoid blocking the event loop.
"""

from __future__ import annotations

import asyncio
import gc
import os
from dataclasses import dataclass
from typing import Any, List, Dict
import modcord.configuration.app_configuration as cfg
from modcord.util.logger import get_logger

logger = get_logger("ai_core")
os.environ.setdefault("TORCH_COMPILE_CACHE_DIR", "./torch_compile_cache")



@dataclass
class ModelState:
    """
    Represents the current state of the AI model, including initialization status, availability, and error tracking.

    Attributes:
        init_started (bool): Indicates if initialization has started.
        available (bool): True if the model is available for inference.
        init_error (str | None): Last initialization error message, if any.
    """
    init_started: bool = False
    available: bool = False
    init_error: str | None = None



class InferenceProcessor:
    """
    Core class for managing synchronous vLLM inference with async wrappers for non-blocking, multi-channel generation.

    Handles:
    - Thread-safe model initialization and unloading
    - Batch chat generation with guided decoding (xgrammar)
    - Dynamic system prompt construction
    - Resource cleanup and error handling

    Attributes:
        llm (Any | None): The vLLM model instance.
        sampling_params (Any | None): Default sampling parameters for generation.
        base_system_prompt (str | None): System prompt template for injection.
        state (ModelState): Tracks model state and errors.
        init_lock (asyncio.Lock): Ensures thread-safe operations.
    """

    def __init__(self) -> None:
        """
        Initialize the InferenceProcessor with default state and thread lock.
        """
        self.llm: Any | None = None
        self.sampling_params: Any | None = None
        self.base_system_prompt: str | None = None
        self.state = ModelState()
        self.init_lock = asyncio.Lock()

    def _set_init_error(self, msg: str) -> None:
        """
        Set the initialization error message and mark the model as unavailable.

        Args:
            msg (str): Error message to record.
        """
        self.state.available = False
        self.state.init_error = msg

    async def init_model(self, model: str | None = None) -> bool:
        """
        Asynchronously initialize the vLLM model engine in a thread-safe manner.

        Loads configuration, checks if AI is enabled, prepares sampling parameters, and runs blocking model load in a thread. Ensures only one initialization attempt at a time.

        Args:
            model (str | None): Optional model identifier override.

        Returns:
            bool: True if initialization succeeded, False otherwise.
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
        Synchronously initialize the vLLM model and sampling parameters (runs in a thread).

        Handles GPU configuration, dtype selection, and error logging.

        Args:
            model_id (str): Model identifier.
            sampling_parameters (Dict[str, Any]): Sampling parameters for generation.
            vram_percentage (float): Fraction of GPU memory to use.

        Returns:
            bool: True if model initialized successfully, False otherwise.
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

        Returns:
            bool: True if available, False otherwise.
        """
        return self.state.available

    def get_model_init_error(self) -> str | None:
        """
        Get the last initialization error message, if any.

        Returns:
            str | None: Error message or None.
        """
        return self.state.init_error

    def get_system_prompt(self, server_rules: str = "", channel_guidelines: str = "") -> str:
        """
        Construct the system prompt by injecting server rules and channel guidelines into the template.

        The JSON input payload will contain the channel information including:
        - channel_id: The Discord channel ID
        - channel_name: The name of the channel being moderated

        Args:
            server_rules (str): Server rules to inject.
            channel_guidelines (str): Channel guidelines to inject.

        Returns:
            str: Formatted system prompt string.
        """
        template = self.base_system_prompt or cfg.app_config.system_prompt_template
        template_str = str(template or "")
        rules_str = str(server_rules or "")
        guidelines_str = str(channel_guidelines or "")
        
        # Inject server rules
        if "<|SERVER_RULES_INJECT|>" in template_str:
            template_str = template_str.replace("<|SERVER_RULES_INJECT|>", rules_str)
        elif rules_str:
            template_str = f"{template_str}\n\nServer rules:\n{rules_str}"
        
        # Inject channel guidelines
        if "<|CHANNEL_GUIDELINES_INJECT|>" in template_str:
            template_str = template_str.replace("<|CHANNEL_GUIDELINES_INJECT|>", guidelines_str)
        elif guidelines_str:
            template_str = f"{template_str}\n\nChannel-specific guidelines:\n{guidelines_str}"
        
        return template_str

    async def generate_multi_chat(
        self,
        conversations: List[List[Dict[str, Any]]],
        grammar_strings: List[str]
    ) -> List[str]:
        """
        Asynchronously generate outputs for multiple conversations in a batch using guided decoding.

        Args:
            conversations (List[List[Dict[str, Any]]]): List of message lists for each conversation.
            grammar_strings (List[str]): List of xgrammar strings for guided decoding.

        Returns:
            List[str]: Generated output strings for each conversation.

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
        Synchronously generate outputs for multiple conversations in a batch (runs in a thread).

        Args:
            conversations (List[List[Dict[str, Any]]]): List of message lists for each conversation.
            grammar_strings (List[str]): List of xgrammar strings for guided decoding.

        Returns:
            List[str]: Generated output strings for each conversation.
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
        Get the current model state object.

        Returns:
            ModelState: The current model state.
        """
        return self.state

    async def unload_model(self) -> None:
        """
        Asynchronously unload the model and clean up resources.

        Resets state attributes and clears GPU memory in a thread-safe manner.
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
        Synchronously clean up GPU memory and run garbage collection (runs in a thread).

        Calls torch.cuda.empty_cache() if available and runs Python garbage collection.
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