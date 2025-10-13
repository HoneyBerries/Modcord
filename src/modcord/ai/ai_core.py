"""
Fully async, self-contained vLLM-backed AI model module for moderation.
Includes model initialization, inference, warmup, and JSON parsing.

IMPORTANT: This module uses lazy imports for AI libraries (torch, vllm, transformers)
to avoid loading heavy dependencies when AI features are disabled. The libraries are
only imported inside functions when AI is actually enabled in the configuration.
This significantly reduces startup time and memory usage when running as a regular
Discord bot without AI moderation features.
"""
from __future__ import annotations

import asyncio
import gc
import os
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

# Use TYPE_CHECKING to avoid runtime imports of AI libraries
# These imports are only for type hints and will not execute at runtime
if TYPE_CHECKING:
    import torch
    from vllm import LLM, SamplingParams
    from vllm.sampling_params import GuidedDecodingParams

import modcord.configuration.app_configuration as cfg
from modcord.util.logger import get_logger
import modcord.util.moderation_parsing as moderation_parsing

logger = get_logger("ai_core")

# Module-level variables for testability (allow monkeypatching)
LLM = None
SamplingParams = None
# Create a minimal torch object with cuda attribute for tests
class _FakeCuda:
    @staticmethod
    def is_available():
        return False
    @staticmethod
    def device_count():
        return 0
    @staticmethod
    def synchronize():
        pass
    @staticmethod
    def empty_cache():
        pass
    @staticmethod
    def ipc_collect():
        pass
class _FakeTorch:
    cuda = _FakeCuda()
    # Add distributed attribute for tests
    class _FakeDist:
        @staticmethod
        def is_available():
            return False
        @staticmethod
        def is_initialized():
            return False
    distributed = _FakeDist()
torch = _FakeTorch()

# ========= State Containers =========


class ModelState:
    def __init__(self) -> None:
        """Initialize bookkeeping flags describing the current model lifecycle state."""
        self.init_started: bool = False
        self.available: bool = False
        self.init_error: Optional[str] = None


class InferenceProcessor:
    """Manage lifecycle and inference for the vLLM-backed moderation model.

    This class handles initialization, configuration, and synchronous-to-
    asynchronous bridging for the vLLM model. Consumers should call
    ``init_model`` before running inference and use ``generate_text`` to
    perform generation from async code.
    """

    def __init__(self) -> None:
        """Instantiate the inference processor with default sampling configuration."""
        self.llm: Optional[Any] = None  # vllm.LLM when loaded
        self.sampling_params: Optional[Any] = None  # vllm.SamplingParams when loaded
        self.base_system_prompt: Optional[str] = None
        self.state = ModelState()
        self.init_lock = asyncio.Lock()
        self.warmup_completed: bool = False
        self.guided_backend: Optional[str] = None
        self._guided_grammar: Optional[str] = None

    def _build_guided_decoding(self) -> Any:
        """Construct the structured outputs configuration for JSON schema enforcement.
        
        This is the primary method that can be mocked in tests.
        """
        # Import here to avoid loading vllm when AI is disabled
        from vllm.sampling_params import StructuredOutputsParams

        schema = moderation_parsing.moderation_schema

        # Use JSON schema directly for structured outputs
        params = StructuredOutputsParams(json=schema)
        logger.info("[AI MODEL] Structured outputs configured with JSON schema")
        return params

    def _build_structured_outputs(self) -> Any:  # Returns StructuredOutputsParams
        """Construct the structured outputs configuration (delegates to _build_guided_decoding)."""
        return self._build_guided_decoding()

    # ======== Model Initialization ========
    async def init_model(self, model: Optional[str] = None) -> Tuple[Optional[Any], Optional[Any], Optional[str]]:
        """Load the vLLM model and return its handles along with any initialization error.

        Parameters
        ----------
        model:
            Optional model identifier overriding the configured default.

        Returns
        -------
        tuple[Optional[Any], Optional[Any], Optional[str]]
            Model instance, sampling parameters, and an initialization error if one occurred.
        """
        async with self.init_lock:
            if self.state.available and self.llm is not None and self.sampling_params is not None:
                return self.llm, self.sampling_params, self.base_system_prompt

            if self.state.init_started and not self.state.available and self.state.init_error:
                return self.llm, self.sampling_params, self.base_system_prompt

            self.state.init_started = True

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

            # Import AI libraries only when AI is enabled
            # Use module-level variables if set (for tests), otherwise import
            global LLM, SamplingParams, torch
            if LLM is None or SamplingParams is None or not hasattr(torch, '__module__'):
                try:
                    import torch as torch_module
                    from vllm import LLM as LLM_class, SamplingParams as SamplingParams_class
                    torch = torch_module
                    LLM = LLM_class
                    SamplingParams = SamplingParams_class
                except ImportError as e:
                    logger.error("[AI MODEL] Failed to import AI libraries: %s", e, exc_info=True)
                    self.state.available = False
                    self.state.init_error = f"AI libraries not available: {e}"
                    return None, None, self.base_system_prompt

            cuda_available = torch.cuda.is_available()
            tp: int = torch.cuda.device_count() if cuda_available else 0

            if is_gpu_allowed and not cuda_available:
                logger.warning("[AI MODEL] GPU allowed but CUDA not available. Using CPU.")

            try:
                gpu_mem_util = vram_percentage if is_gpu_allowed and cuda_available else 0.0
                logger.info(
                    "[AI MODEL] Loading vLLM model '%s' (dtype=%s, tp=%s, gpu_mem=%s)",
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

                def build_llm() -> Any:  # Returns LLM
                    return LLM(
                        model=model_identifier,
                        dtype=dtype,
                        gpu_memory_utilization=gpu_mem_util,
                        max_model_len=max_model_length,
                        tensor_parallel_size=tp,
                    )

                self.llm = await asyncio.to_thread(build_llm)

                # For Qwen3-Thinking models, we rely on prompt engineering + parsing
                # to handle reasoning (up to 256 tokens) followed by JSON output.
                # 
                # NOTE: The 256-token reasoning limit is enforced via:
                # 1. System prompt instruction (soft limit - model should follow)
                # 2. max_tokens=512 in SamplingParams (hard limit on total output)
                #    This allows ~256 tokens for reasoning + ~256 for JSON output
                #
                # For a hard per-phase limit, you would need vllm serve with:
                #   --enable-reasoning --max-reasoning-tokens 256
                # But that's not available with the offline LLM API.
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
                logger.info("[AI MODEL] vLLM initialized successfully.")
                return self.llm, self.sampling_params, self.base_system_prompt

            except Exception as e:
                self.state.available = False
                self.state.init_error = f"Initialization failed: {e}"
                logger.error(f"[AI MODEL] Failed to initialize vLLM model: {e}", exc_info=True)
                return None, None, self.base_system_prompt

    # ======== Model Accessors ========
    async def get_model(self) -> Tuple[Optional[Any], Optional[Any], Optional[str]]:
        """Return the cached vLLM model and sampling parameters, if initialization succeeded.

        Returns
        -------
        tuple[Optional[Any], Optional[Any], Optional[str]]
            Cached model, sampling configuration, and last recorded error.
        """
        if self.llm is None and not self.state.init_started:
            await self.init_model()
        return self.llm, self.sampling_params, self.base_system_prompt

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
    def sync_generate(self, prompts: List[str]) -> List[str]:
        """Synchronous wrapper around the model's generate API.

        This runs in the calling thread and is intended to be invoked from
        a threadpool via ``asyncio.to_thread`` by async callers.
        """
        if self.llm is None or self.sampling_params is None:
            raise RuntimeError("Model not initialized")

        outputs = self.llm.generate(prompts, self.sampling_params)

        logger.debug("[AI MODEL] Generated outputs: %s", [o.outputs[0].text.strip() if o.outputs else "" for o in outputs])

        results = []
        for out in outputs:
            results.append(out.outputs[0].text.strip() if out.outputs else "")
        return results

    async def generate_text(self, prompts: List[str]) -> List[str]:
        """Asynchronously generate text for the supplied prompts.

        Ensures the model is initialized and delegates heavy work to a
        threadpool so callers need not block the event loop.
        """
        model, params, _ = await self.get_model()
        if model is None or params is None:
            reason = self.state.init_error or "AI model unavailable"
            raise RuntimeError(reason)

        return await asyncio.to_thread(self.sync_generate, prompts)

    # ======== State Accessors ========
    def get_model_state(self) -> ModelState:
        """Return the internal ModelState object for inspection.

        Useful for health checks and startup diagnostics.
        """
        return self.state

    async def unload_model(self) -> None:
        """Release the underlying vLLM engine and reset state flags."""

        async with self.init_lock:
            llm = self.llm
            self.llm = None
            self.sampling_params = None
            self.state.available = False
            self.state.init_started = False
            self.state.init_error = None
            self.warmup_completed = False
            self.guided_backend = None
            self._guided_grammar = None

        if llm is not None:
            try:
                engine = getattr(llm, "llm_engine", None)
                if engine is not None:
                    structured_manager = getattr(engine, "structured_output_manager", None)
                    if structured_manager is not None and hasattr(structured_manager, "clear_backend"):
                        try:
                            structured_manager.clear_backend()
                        except Exception as exc:
                            logger.debug(
                                "[AI MODEL] Failed to clear structured output backend during unload: %s",
                                exc,
                                exc_info=True,
                            )
                    if hasattr(engine, "shutdown"):
                        await asyncio.to_thread(engine.shutdown)
                if engine is not None:
                    try:
                        setattr(llm, "llm_engine", None)
                    except Exception:
                        pass
            except Exception as exc:  # noqa: BLE001 - best effort cleanup
                logger.warning("[AI MODEL] Error while shutting down vLLM engine: %s", exc, exc_info=True)
            finally:
                llm = None

        try:
            # Import torch only if needed for cleanup
            import torch

            if torch.cuda.is_available():  # pragma: no branch - defensive cleanup
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
        except ImportError:
            # torch not available, skip CUDA cleanup
            pass
        except Exception as exc:  # noqa: BLE001 - ignore cleanup failures
            logger.debug("[AI MODEL] Failed to clear CUDA cache during unload: %s", exc, exc_info=True)

        try:
            import torch.distributed as dist

            if dist.is_available() and dist.is_initialized():
                dist.destroy_process_group(dist.group.WORLD)
        except ImportError:
            # torch.distributed not available, skip cleanup
            pass
        except Exception as exc:  # noqa: BLE001 - optional cleanup
            logger.warning("[AI MODEL] torch.distributed cleanup failed during unload: %s", exc, exc_info=True)

        gc.collect()


inference_processor = InferenceProcessor()
model_state = inference_processor.state