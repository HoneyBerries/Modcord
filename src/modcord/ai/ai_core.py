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
    """Manage model lifecycle and inference calls."""

    def __init__(self) -> None:
        self.engine: Optional[Any] = None
        self.sampling_params: Optional[Any] = None
        self.base_system_prompt: Optional[str] = None
        self.state = ModelState()
        self.init_lock = asyncio.Lock()
        self.warmup_completed = False

    def _build_structured_outputs(self) -> Any:
        from vllm.sampling_params import StructuredOutputsParams

        return StructuredOutputsParams(json=moderation_parsing.moderation_schema)

    async def init_model(self, model: Optional[str] = None) -> Tuple[Optional[Any], Optional[Any], Optional[str]]:
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
            except ImportError as exc:  # noqa: PERF203
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
                )

                self.engine = AsyncLLMEngine.from_engine_args(engine_args)
                self.sampling_params = SamplingParams(
                    temperature=knobs["temperature"],
                    max_tokens=knobs["max_new_tokens"],
                    top_p=knobs["top_p"],
                    top_k=knobs["top_k"],
                    repetition_penalty=knobs["repetition_penalty"],
                    presence_penalty=knobs["presence_penalty"],
                    frequency_penalty=knobs["frequency_penalty"],
                    structured_outputs=self._build_structured_outputs(),
                )
            except Exception as exc:  # noqa: BLE001
                self.state.available = False
                self.state.init_error = f"Initialization failed: {exc}"
                logger.error("[AI MODEL] AsyncLLMEngine initialization failed: %s", exc)
                return None, None, self.base_system_prompt

            self.state.available = True
            self.state.init_error = None
            logger.info("[AI MODEL] Model '%s' initialized", model_id)
            return self.engine, self.sampling_params, self.base_system_prompt

    async def get_model(self) -> Tuple[Optional[Any], Optional[Any], Optional[str]]:
        if not self.state.init_started:
            await self.init_model()
        return self.engine, self.sampling_params, self.base_system_prompt

    async def is_model_available(self) -> bool:
        return self.state.available

    async def get_model_init_error(self) -> Optional[str]:
        return self.state.init_error

    async def get_system_prompt(self, server_rules: str = "") -> str:
        await self.get_model()
        template = self.base_system_prompt or cfg.app_config.system_prompt_template
        return cfg.app_config.format_system_prompt(server_rules, template_override=template)

    async def generate_text(self, prompts: List[str]) -> List[str]:
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
        return self.state

    async def unload_model(self) -> None:
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
            except Exception as exc:  # noqa: BLE001
                logger.warning("[AI MODEL] Shutdown raised: %s", exc)

        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
        except Exception as exc:  # noqa: BLE001
            logger.debug("[AI MODEL] CUDA cache cleanup failed: %s", exc)

        gc.collect()
        logger.info("[AI MODEL] Model unloaded")


inference_processor = InferenceProcessor()
model_state = inference_processor.state

