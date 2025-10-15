"""
Fully async, self-contained vLLM-backed AI model module for moderation.
Includes model initialization, inference, warmup, and JSON parsing.

This module now uses vLLM's native AsyncLLMEngine for fully async inference
without any synchronous wrappers or thread pools.

Architecture:
-------------
- AsyncLLMEngine: vLLM's native async engine for non-blocking inference
- AsyncEngineArgs: Configuration class for engine initialization
- SamplingParams: Controls generation behavior (temperature, top_p, etc.)
- StructuredOutputsParams: Enforces JSON schema compliance in outputs

Key Features:
-------------
1. Fully Async: All operations use native async/await without thread pools
2. Lazy Imports: AI libraries (torch, vllm) only loaded when AI is enabled
3. Structured Outputs: JSON schema enforcement for reliable moderation data
4. Batch Processing: Efficient concurrent generation for multiple prompts
5. State Management: Thread-safe initialization and lifecycle tracking

Usage Example:
--------------
    # Initialize the processor
    processor = InferenceProcessor()
    
    # Initialize the model (happens once)
    engine, params, prompt = await processor.init_model()
    
    # Check if model is ready
    if await processor.is_model_available():
        # Generate responses for multiple prompts
        prompts = ["Review this message", "Check this content"]
        results = await processor.generate_text(prompts)
        
    # Clean up when done
    await processor.unload_model()

Migration from Synchronous LLM:
--------------------------------
Old synchronous approach:
    llm = LLM(model=..., dtype=..., gpu_memory_utilization=...)
    outputs = await asyncio.to_thread(llm.generate, prompts, sampling_params)

New async approach:
    engine_args = AsyncEngineArgs(model=..., dtype=..., gpu_memory_utilization=...)
    engine = await AsyncLLMEngine.from_engine_args(engine_args)
    
    async def generate_one(prompt):
        async for output in engine.generate(prompt, sampling_params, request_id):
            pass  # Collect outputs
        return output
    
    results = await asyncio.gather(*[generate_one(p) for p in prompts])

IMPORTANT: This module uses lazy imports for AI libraries (torch, vllm, transformers)
to avoid loading heavy dependencies when AI features are disabled. The libraries are
only imported inside functions when AI is actually enabled in the configuration.
This significantly reduces startup time and memory usage when running as a regular
Discord bot without AI moderation features.
"""
from __future__ import annotations

import asyncio
import gc
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

# Use TYPE_CHECKING to avoid runtime imports of AI libraries
# These imports are only for type hints and will not execute at runtime
if TYPE_CHECKING:
    import torch
    from vllm.engine.async_llm_engine import AsyncLLMEngine
    from vllm import SamplingParams
    from vllm.sampling_params import GuidedDecodingParams

import modcord.configuration.app_configuration as cfg
from modcord.util.logger import get_logger
import modcord.util.moderation_parsing as moderation_parsing

logger = get_logger("ai_core")

# ========= State Containers =========


class ModelState:
    def __init__(self) -> None:
        """Initialize bookkeeping flags describing the current model lifecycle state."""
        self.init_started: bool = False
        self.available: bool = False
        self.init_error: Optional[str] = None


class InferenceProcessor:
    """Manage lifecycle and inference for the vLLM-backed moderation model.

    This class handles async initialization, configuration, and inference using
    vLLM's native AsyncLLMEngine. All operations are fully async without thread pools.
    Consumers should call ``init_model`` before running inference and use 
    ``generate_text`` to perform batch generation from async code.
    """

    def __init__(self) -> None:
        """Instantiate the inference processor with default sampling configuration."""
        self.engine: Optional[Any] = None  # AsyncLLMEngine when loaded
        self.sampling_params: Optional[Any] = None  # vllm.SamplingParams when loaded
        self.base_system_prompt: Optional[str] = None
        self.state = ModelState()
        self.init_lock = asyncio.Lock()
        self.warmup_completed: bool = False

    def _build_structured_outputs(self) -> Any:  # Returns StructuredOutputsParams
        """Construct the structured outputs configuration for JSON schema enforcement."""
        # Import here to avoid loading vllm when AI is disabled
        from vllm.sampling_params import StructuredOutputsParams

        schema = moderation_parsing.moderation_schema

        # Use JSON schema directly for structured outputs
        params = StructuredOutputsParams(json=schema)
        logger.info("[AI MODEL] Structured outputs configured with JSON schema")
        return params

    # ======== Model Initialization ========
    async def init_model(self, model: Optional[str] = None) -> Tuple[Optional[Any], Optional[Any], Optional[str]]:
        """Load the vLLM AsyncLLMEngine and return its handles along with any initialization error.

        Parameters
        ----------
        model:
            Optional model identifier overriding the configured default.

        Returns
        -------
        tuple[Optional[Any], Optional[Any], Optional[str]]
            Engine instance, sampling parameters, and an initialization error if one occurred.
        """
        async with self.init_lock:
            # Return cached engine if already initialized
            if self.state.available and self.engine is not None and self.sampling_params is not None:
                return self.engine, self.sampling_params, self.base_system_prompt

            # Return early if initialization previously failed
            if self.state.init_started and not self.state.available and self.state.init_error:
                return self.engine, self.sampling_params, self.base_system_prompt

            self.state.init_started = True

            # Load and validate configuration
            base_configuration = cfg.app_config.reload()
            if not base_configuration:
                logger.error("[AI MODEL] Configuration is empty; cannot initialize AI model.")
                self.state.init_error = "missing configuration"
                self.state.available = False
                return None, None, None

            self.base_system_prompt = cfg.app_config.system_prompt_template
            ai_configuration = cfg.app_config.ai_settings
            is_ai_enabled = bool(ai_configuration.get("enabled", False))
            is_gpu_allowed = bool(ai_configuration.get("allow_gpu", False))
            vram_percentage = ai_configuration.get("vram_percentage", 0.5)
            model_identifier = model or ai_configuration.get("model_id")

            # Extract sampling and model configuration knobs
            knobs = ai_configuration.get("knobs", {})
            dtype = knobs.get("dtype", "auto")
            max_new_tokens = knobs.get("max_new_tokens", 256)
            max_model_length = knobs.get("max_model_length", 2048)
            temperature = knobs.get("temperature", 1.0)
            top_p = knobs.get("top_p", 1.0)
            top_k = knobs.get("top_k", -1)
            repetition_penalty = knobs.get("repetition_penalty", 1.0)
            presence_penalty = knobs.get("presence_penalty", 0.0)
            frequency_penalty = knobs.get("frequency_penalty", 0.0)

            logger.info("[AI MODEL] Using configuration knobs")
            logger.info(
                "temperature=%s, max_new_tokens=%s, dtype=%s, top_p=%s, top_k=%s, "
                "repetition_penalty=%s, presence_penalty=%s, frequency_penalty=%s",
                temperature,
                max_new_tokens,
                dtype,
                top_p,
                top_k,
                repetition_penalty,
                presence_penalty,
                frequency_penalty,
            )

            if not is_ai_enabled:
                logger.info("[AI MODEL] AI disabled in configuration.")
                self.state.available = False
                self.state.init_error = "AI disabled in config"
                return None, None, self.base_system_prompt

            if not model_identifier:
                logger.error("[AI MODEL] No model identifier provided.")
                self.state.available = False
                self.state.init_error = "missing model id"
                return None, None, self.base_system_prompt

            # Lazy import AI libraries only when AI is enabled
            try:
                import torch
                from vllm.engine.async_llm_engine import AsyncLLMEngine
                from vllm.engine.arg_utils import AsyncEngineArgs
                from vllm import SamplingParams
            except ImportError as e:
                logger.error("[AI MODEL] Failed to import AI libraries: %s", e, exc_info=True)
                self.state.available = False
                self.state.init_error = f"AI libraries not available: {e}"
                return None, None, self.base_system_prompt

            # Check CUDA availability and configure tensor parallelism
            cuda_available = torch.cuda.is_available()
            tp: int = torch.cuda.device_count() if cuda_available else 1

            if is_gpu_allowed and not cuda_available:
                logger.warning("[AI MODEL] GPU allowed but CUDA not available. Using CPU.")

            try:
                # Configure GPU memory utilization based on availability
                gpu_mem_util = vram_percentage if is_gpu_allowed and cuda_available else 0.0
                logger.info(
                    "[AI MODEL] Loading AsyncLLMEngine for model '%s' (dtype=%s, tp=%s, gpu_mem=%s)",
                    model_identifier,
                    dtype,
                    tp,
                    gpu_mem_util,
                )
                logger.info(
                    "[AI MODEL] Config: max_model_len=%s, temperature=%s, top_p=%s",
                    max_model_length,
                    temperature,
                    top_p,
                )

                # Create AsyncEngineArgs with all configuration parameters
                # AsyncEngineArgs is the modern way to configure vLLM engines.
                # It provides a clean interface for all engine settings including:
                # - Model loading (model path, dtype, quantization)
                # - Resource allocation (GPU memory, tensor parallelism)
                # - Performance tuning (CUDA graphs, KV cache)
                # - Trust and security (trust_remote_code for custom models)
                engine_args = AsyncEngineArgs(
                    model=model_identifier,
                    dtype=dtype,
                    gpu_memory_utilization=gpu_mem_util,
                    max_model_len=max_model_length,
                    tensor_parallel_size=tp,
                    trust_remote_code=True,  # Often needed for custom models like Qwen
                    enforce_eager=False,  # Allow CUDA graphs for better performance
                )

                # Initialize AsyncLLMEngine from engine args (fully async, no blocking)
                # This replaces the old LLM() constructor and asyncio.to_thread pattern.
                # from_engine_args() is an async classmethod that initializes the engine
                # without blocking the event loop, making it perfect for async applications.
                logger.info("[AI MODEL] Initializing AsyncLLMEngine...")
                self.engine = await AsyncLLMEngine.from_engine_args(engine_args)

                # Configure sampling parameters with structured outputs for JSON schema
                # For Qwen3-Thinking models, we rely on prompt engineering + parsing
                # to handle reasoning (up to 256 tokens) followed by JSON output.
                # 
                # NOTE: The 256-token reasoning limit is enforced via:
                # 1. System prompt instruction (soft limit - model should follow)
                # 2. max_tokens in SamplingParams (hard limit on total output)
                #    This allows for reasoning + JSON output within the limit
                #
                # Structured outputs via JSON schema will help ensure valid JSON
                structured_outputs = self._build_structured_outputs()

                self.sampling_params = SamplingParams(
                    temperature=temperature,
                    max_tokens=max_new_tokens,
                    top_p=top_p,
                    top_k=top_k,
                    repetition_penalty=repetition_penalty,
                    presence_penalty=presence_penalty,
                    frequency_penalty=frequency_penalty,
                    structured_outputs=structured_outputs,
                )

                self.state.available = True
                self.state.init_error = None
                logger.info("[AI MODEL] AsyncLLMEngine initialized successfully.")
                return self.engine, self.sampling_params, self.base_system_prompt

            except Exception as e:
                self.state.available = False
                self.state.init_error = f"Initialization failed: {e}"
                logger.error(f"[AI MODEL] Failed to initialize AsyncLLMEngine: {e}", exc_info=True)
                return None, None, self.base_system_prompt

    # ======== Model Accessors ========
    async def get_model(self) -> Tuple[Optional[Any], Optional[Any], Optional[str]]:
        """Return the cached AsyncLLMEngine and sampling parameters, if initialization succeeded.

        Returns
        -------
        tuple[Optional[Any], Optional[Any], Optional[str]]
            Cached engine, sampling configuration, and last recorded error.
        """
        if self.engine is None and not self.state.init_started:
            await self.init_model()
        return self.engine, self.sampling_params, self.base_system_prompt

    async def is_model_available(self) -> bool:
        """Return ``True`` when the model has been initialized and is ready for inference."""
        return self.state.available

    async def get_model_init_error(self) -> Optional[str]:
        """Return the last initialization error recorded for the model, if any."""
        return self.state.init_error

    async def get_system_prompt(self, server_rules: str = "") -> str:
        """Return the system prompt template tailored to the provided server rules.

        Parameters
        ----------
        server_rules:
            Optional text describing guild-specific moderation rules.

        Returns
        -------
        str
            System prompt string to prepend to moderation requests.
        """
        await self.get_model()
        template = self.base_system_prompt or cfg.app_config.system_prompt_template
        return cfg.app_config.format_system_prompt(server_rules, template_override=template)

    # ======== Inference Helpers ========
    async def generate_text(self, prompts: List[str]) -> List[str]:
        """Asynchronously generate text for the supplied prompts using AsyncLLMEngine.

        This method uses native async generation without thread pools. It submits
        all prompts concurrently to the engine and collects final outputs.
        
        Implementation Details:
        -----------------------
        AsyncLLMEngine.generate() returns an async generator that yields intermediate
        results as generation progresses. For each prompt, we:
        1. Create a unique request ID
        2. Submit the prompt to the engine
        3. Iterate through the async generator to get updates
        4. Extract the final output when generation completes
        
        All prompts are processed concurrently using asyncio.gather(), allowing
        the engine to batch them efficiently for maximum throughput.

        Parameters
        ----------
        prompts:
            List of prompt strings to generate completions for.

        Returns
        -------
        list[str]
            Generated text completions, one per prompt in the same order.
            
        Raises
        ------
        RuntimeError:
            If the model is not initialized or unavailable.
        """
        # Ensure model is initialized
        engine, params, _ = await self.get_model()
        if engine is None or params is None:
            reason = self.state.init_error or "AI model unavailable"
            raise RuntimeError(reason)

        # Submit all prompts to the engine concurrently and collect results
        results: List[str] = []
        
        # Create async tasks for each prompt generation
        async def generate_single(prompt: str, request_id: str) -> str:
            """Generate completion for a single prompt and extract final text.
            
            AsyncLLMEngine.generate() is an async generator that yields RequestOutput
            objects as tokens are generated. We iterate through all outputs and keep
            the final one, which contains the complete generated text.
            """
            final_output = None
            
            # AsyncLLMEngine.generate returns an async generator that yields results
            # as generation progresses. We iterate until completion.
            async for request_output in engine.generate(
                prompt=prompt,
                sampling_params=params,
                request_id=request_id,
            ):
                # Keep updating with latest output until generation completes
                final_output = request_output
            
            # Extract text from the final output
            if final_output and final_output.outputs:
                text = final_output.outputs[0].text.strip()
                logger.debug("[AI MODEL] Generated output for request %s: %s", request_id, text[:100])
                return text
            return ""
        
        # Generate unique request IDs for each prompt to track them in the engine
        tasks = [
            generate_single(prompt, f"moderation-{uuid.uuid4().hex}")
            for prompt in prompts
        ]
        
        # Run all generations concurrently and collect results in order
        results = await asyncio.gather(*tasks)
        
        logger.debug("[AI MODEL] Generated %d outputs", len(results))
        return results

    # ======== State Accessors ========
    def get_model_state(self) -> ModelState:
        """Return the internal ModelState object for inspection.

        Useful for health checks and startup diagnostics.
        """
        return self.state

    async def unload_model(self) -> None:
        """Release the underlying AsyncLLMEngine and reset state flags.
        
        This method gracefully shuts down the async engine and clears GPU memory.
        """
        async with self.init_lock:
            engine = self.engine
            self.engine = None
            self.sampling_params = None
            self.state.available = False
            self.state.init_started = False
            self.state.init_error = None
            self.warmup_completed = False

        # Shut down the AsyncLLMEngine if it exists
        if engine is not None:
            try:
                # AsyncLLMEngine has an async shutdown method
                if hasattr(engine, 'shutdown'):
                    await engine.shutdown()
                    logger.info("[AI MODEL] AsyncLLMEngine shut down successfully")
            except Exception as exc:
                logger.warning("[AI MODEL] Error while shutting down AsyncLLMEngine: %s", exc, exc_info=True)
            finally:
                engine = None

        # Clear CUDA cache if torch is available
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
                logger.debug("[AI MODEL] CUDA cache cleared")
        except ImportError:
            # torch not available, skip CUDA cleanup
            pass
        except Exception as exc:
            logger.debug("[AI MODEL] Failed to clear CUDA cache during unload: %s", exc, exc_info=True)

        # Clean up distributed processes if needed
        try:
            import torch.distributed as dist

            if dist.is_available() and dist.is_initialized():
                dist.destroy_process_group(dist.group.WORLD)
                logger.debug("[AI MODEL] Distributed process group destroyed")
        except ImportError:
            # torch.distributed not available, skip cleanup
            pass
        except Exception as exc:
            logger.warning("[AI MODEL] torch.distributed cleanup failed during unload: %s", exc, exc_info=True)

        # Force garbage collection to free memory
        gc.collect()
        logger.info("[AI MODEL] Model unloaded and memory released")


inference_processor = InferenceProcessor()
model_state = inference_processor.state