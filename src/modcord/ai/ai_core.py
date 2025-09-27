"""
Fully async, self-contained vLLM-backed AI model module for moderation.
Includes model initialization, inference, warmup, and JSON parsing.
"""
from __future__ import annotations

import asyncio
from typing import List, Optional, Tuple

import torch
from vllm import LLM, SamplingParams
from vllm.sampling_params import GuidedDecodingParams

import modcord.configuration.app_configuration as cfg
from modcord.util.logger import get_logger
import modcord.util.moderation_parsing as moderation_parsing

logger = get_logger("ai_core")

# ========= State Containers =========


class ModelState:
    def __init__(self) -> None:
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
        self.llm: Optional[LLM] = None
        self.sampling_params: Optional[SamplingParams] = None
        self.base_system_prompt: Optional[str] = None
        self.state = ModelState()
        self.init_lock = asyncio.Lock()
        self.warmup_completed: bool = False

    # ======== Model Initialization ========
    async def init_model(self, model: Optional[str] = None) -> Tuple[Optional[LLM], Optional[SamplingParams], Optional[str]]:
        """Initialize or reload the underlying LLM.

        Args:
            model: Optional model identifier to override configuration.

        Returns:
            A tuple of (llm, sampling_params, base_system_prompt) on success
            or (None, None, template) on failure.
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
            logger.debug(
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

                self.llm = LLM(
                    model=model_identifier,
                    dtype=dtype,
                    gpu_memory_utilization=gpu_mem_util,
                    max_model_len=max_model_length,
                    tensor_parallel_size=tp,
                )

                self.sampling_params = SamplingParams(
                    temperature=temperature,
                    max_tokens=max_new_tokens,
                    top_p=top_p,
                    top_k=top_k,
                    repetition_penalty=repetition_penalty,
                    presence_penalty=presence_penalty,
                    frequency_penalty=frequency_penalty,
                    guided_decoding=GuidedDecodingParams
                    (json=moderation_parsing.moderation_schema),
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

    async def get_model(self) -> Tuple[Optional[LLM], Optional[SamplingParams], Optional[str]]:
        """Return the current model and sampling parameters.

        Automatically triggers initialization if it has not started.
        """
        if self.llm is None and not self.state.init_started:
            await self.init_model()
        return self.llm, self.sampling_params, self.base_system_prompt

    async def is_model_available(self) -> bool:
        """Return True when the model is initialized and ready for inference."""
        return self.state.available

    async def get_model_init_error(self) -> Optional[str]:
        """Return the textual initialization error if initialization failed."""
        return self.state.init_error

    async def get_system_prompt(self, server_rules: str = "") -> str:
        """Format and return the system prompt for the model.

        The prompt is built from the configured system template and the
        optionally-supplied server-specific rules.
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


inference_processor = InferenceProcessor()
model_state = inference_processor.state