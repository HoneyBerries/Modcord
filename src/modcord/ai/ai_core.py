"""Async moderation model core backed by vLLM."""

from __future__ import annotations

import asyncio
import gc
import os
import uuid
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

import modcord.configuration.app_configuration as cfg
import modcord.util.moderation_parsing as moderation_parsing
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
    Asynchronous moderation model core backed by vLLM with guided decoding.

    Manages the lifecycle and inference operations of an AI model for moderation tasks.
    Uses xgrammar-based guided decoding to enforce JSON schema compliance while allowing
    free-form reasoning before structured output.

    Core Responsibilities:
        - Handles initialization, configuration, and unloading of the vLLM async engine
        - Manages concurrency for model initialization using an asyncio lock
        - Loads model configuration and sampling parameters from application settings
        - Configures guided decoding with xgrammar backend for JSON schema enforcement
        - Provides methods to check model availability and retrieve initialization errors
        - Formats and returns system prompts with server rules injection
        - Generates text outputs asynchronously using the loaded model
        - Cleans up resources and GPU memory upon model unload

    Attributes:
        engine (Optional[Any]): The AsyncLLMEngine instance.
        sampling_params (Optional[Any]): SamplingParams with guided decoding configuration.
        base_system_prompt (Optional[str]): The base system prompt template.
        state (ModelState): Tracks model state, availability, and errors.
        init_lock (asyncio.Lock): Ensures thread-safe model initialization.
        warmup_completed (bool): Indicates if the model warmup is complete.
        guided_backend (Optional[str]): The guided decoding backend name (xgrammar).
        _guided_grammar (Optional[str]): Cached compiled grammar string for reuse.
    """

    def __init__(self) -> None:
        """
        Initializes the InferenceProcessor with default state and guided decoding support.
        """
        self.engine: Optional[Any] = None
        self.sampling_params: Optional[Any] = None
        self.base_system_prompt: Optional[str] = None
        self.state = ModelState()
        self.init_lock = asyncio.Lock()
        self.warmup_completed = False
        self.guided_backend: Optional[str] = None
        self._guided_grammar: Optional[str] = None

    def _build_guided_decoding(self) -> Any:
        """
        Constructs guided decoding configuration for JSON schema enforcement.
        
        Uses xgrammar backend to compile the moderation schema into a grammar that
        constrains model generation. The compiled grammar is cached for reuse across
        inference calls. Supports models with or without reasoning capabilities.

        Returns:
            GuidedDecodingParams: Configured with compiled grammar and fallback disabled.

        Raises:
            RuntimeError: If xgrammar backend is not available.
        """
        from vllm.sampling_params import GuidedDecodingParams
        
        schema = moderation_parsing.moderation_schema

        if self._guided_grammar is None:
            try:
                from xgrammar import Grammar  # type: ignore
            except Exception as exc:
                raise RuntimeError("xgrammar backend not available for guided decoding") from exc

            try:
                grammar_obj: Optional[Any] = Grammar.from_json_schema(schema, strict_mode=True)
                grammar_str = str(grammar_obj)
                self._guided_grammar = grammar_str
            finally:
                # Ensure any intermediate native handles can be cleaned up
                grammar_obj = None

        params = GuidedDecodingParams(
            grammar=self._guided_grammar,
            disable_fallback=True,
        )
        self.guided_backend = "xgrammar"
        logger.info("[AI MODEL] Guided decoding configured with xgrammar backend (precompiled grammar)")
        return params


    async def init_model(self, model: Optional[str] = None) -> Tuple[Optional[Any], Optional[Any], Optional[str]]:
        """
        Initializes the vLLM async engine with guided decoding support.

        Args:
            model: Optional model identifier override.

        Returns:
            Tuple of (engine, sampling_params, system_prompt). Returns None for engine/params
            if initialization fails, with error details in self.state.init_error.
        """
        async with self.init_lock:
            if self.state.available and self.engine and self.sampling_params:
                return self.engine, self.sampling_params, self.base_system_prompt

            if self.state.init_started and self.state.init_error and not self.state.available:
                return self.engine, self.sampling_params, self.base_system_prompt

            self.state.init_started = True

            base_config = cfg.app_config.reload()
            if not base_config:
                self.base_system_prompt = None
                self.state.available = False
                self.state.init_error = "missing configuration"
                return None, None, None

            self.base_system_prompt = cfg.app_config.system_prompt_template
            ai_config = cfg.app_config.ai_settings or {}

            if not ai_config.get("enabled", False):
                self.state.available = False
                self.state.init_error = "AI disabled in config"
                return None, None, self.base_system_prompt

            model_id = model or ai_config.get("model_id")
            if not model_id:
                self.state.available = False
                self.state.init_error = "missing model id"
                return None, None, self.base_system_prompt

            knobs_defaults = {
                "dtype": "auto",
                "max_new_tokens": 256,
                "max_model_length": 2048,
                "temperature": 1.0,
                "top_p": 1.0,
                "top_k": -1,
                "repetition_penalty": 1.0,
                "presence_penalty": 0.0,
                "frequency_penalty": 0.0,
            }
            knobs = {**knobs_defaults, **(ai_config.get("knobs") or {})}

            allow_gpu = bool(ai_config.get("allow_gpu", False))
            vram_percentage = float(ai_config.get("vram_percentage", 0.5))

            try:
                import torch
                from vllm import SamplingParams
                from vllm.engine.async_llm_engine import AsyncLLMEngine
                from vllm.engine.arg_utils import AsyncEngineArgs
            except ImportError as exc:
                self.state.available = False
                self.state.init_error = f"AI libraries not available: {exc}"
                logger.error("[AI MODEL] vLLM imports failed: %s", exc)
                return None, None, self.base_system_prompt

            cuda_available = torch.cuda.is_available()
            tensor_parallel = torch.cuda.device_count() if cuda_available else 1
            gpu_mem_util = vram_percentage if allow_gpu and cuda_available else 0.0

            try:
                engine_args = AsyncEngineArgs(
                    model=model_id,
                    dtype=knobs["dtype"],
                    gpu_memory_utilization=gpu_mem_util,
                    max_model_len=knobs["max_model_length"],
                    tensor_parallel_size=tensor_parallel,
                    trust_remote_code=True,
                    guided_decoding_backend="xgrammar",
                    guided_decoding_disable_fallback=True,
                )

                self.engine = AsyncLLMEngine.from_engine_args(engine_args)
                
                # Build guided decoding params for JSON schema enforcement
                guided_decoding = self._build_guided_decoding()
                
                self.sampling_params = SamplingParams(
                    temperature=knobs["temperature"],
                    max_tokens=knobs["max_new_tokens"],
                    top_p=knobs["top_p"],
                    top_k=knobs["top_k"],
                    repetition_penalty=knobs["repetition_penalty"],
                    presence_penalty=knobs["presence_penalty"],
                    frequency_penalty=knobs["frequency_penalty"],
                    guided_decoding=guided_decoding,
                )
                logger.info("[AI MODEL] Sampling params created with guided_decoding (xgrammar backend)")
            except Exception as exc:
                self.state.available = False
                self.state.init_error = f"Initialization failed: {exc}"
                logger.error("[AI MODEL] AsyncLLMEngine initialization failed: %s", exc)
                return None, None, self.base_system_prompt

            self.state.available = True
            self.state.init_error = None
            logger.info("[AI MODEL] Model '%s' initialized", model_id)
            return self.engine, self.sampling_params, self.base_system_prompt

    async def get_model(self) -> Tuple[Optional[Any], Optional[Any], Optional[str]]:
        """
        Ensures the model is initialized and returns engine handles.

        Returns:
            Tuple of (engine, sampling_params, system_prompt).
        """
        if not self.state.init_started:
            await self.init_model()
        return self.engine, self.sampling_params, self.base_system_prompt

    async def is_model_available(self) -> bool:
        """Checks if the model is available for inference."""
        return self.state.available

    async def get_model_init_error(self) -> Optional[str]:
        """Retrieves the last initialization error, if any."""
        return self.state.init_error

    async def get_system_prompt(self, server_rules: str = "") -> str:
        """
        Returns the system prompt with server rules injected.

        Args:
            server_rules: Server rules to inject into the <|SERVER_RULES|> placeholder.

        Returns:
            Formatted system prompt string with rules inserted.
        """
        await self.get_model()
        template = self.base_system_prompt or cfg.app_config.system_prompt_template
        template_str = str(template or "")
        rules_str = str(server_rules or "")
        
        # Simple string replacement - supports <|SERVER_RULES|> placeholder format
        if "<|SERVER_RULES|>" in template_str:
            return template_str.replace("<|SERVER_RULES|>", rules_str)
        
        # Fallback: append rules if no placeholder found
        if rules_str:
            return f"{template_str}\n\nServer rules:\n{rules_str}"
        return template_str

    async def generate_text(self, prompts: List[str]) -> List[str]:
        """
        Generates text outputs asynchronously using the model with guided decoding.

        Args:
            prompts: List of input prompt strings.

        Returns:
            List of generated output strings (JSON constrained by schema).

        Raises:
            RuntimeError: If the model is not available or initialization failed.
        """
        engine, params, _ = await self.get_model()
        if not engine or not params:
            reason = self.state.init_error or "AI model unavailable"
            raise RuntimeError(reason)

        async def run_single(prompt: str) -> str:
            request_id = f"moderation-{uuid.uuid4().hex}"
            final_output = None
            async for output in engine.generate(
                prompt=prompt,
                sampling_params=params,
                request_id=request_id,
            ):
                final_output = output
            if final_output and final_output.outputs:
                return final_output.outputs[0].text.strip()
            return ""

        return await asyncio.gather(*(run_single(prompt) for prompt in prompts))

    def get_model_state(self) -> ModelState:
        """Returns the current model state."""
        return self.state

    async def unload_model(self) -> None:
        """
        Unloads the model and cleans up resources.
        
        Shuts down the engine, clears GPU memory, and resets all state attributes.
        """
        async with self.init_lock:
            engine = self.engine
            self.engine = None
            self.sampling_params = None
            self.state.available = False
            self.state.init_started = False
            self.state.init_error = None
            self.warmup_completed = False

        if engine and hasattr(engine, "shutdown"):
            try:
                await engine.shutdown()
            except Exception as exc:
                logger.warning("[AI MODEL] Shutdown raised: %s", exc)

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