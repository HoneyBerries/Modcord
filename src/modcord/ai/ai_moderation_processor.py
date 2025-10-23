"""High-level orchestration logic for AI-driven moderation workflows."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from modcord.ai.ai_core import InferenceProcessor, inference_processor
from modcord.util.logger import get_logger
from modcord.moderation.moderation_datatypes import (
    ActionData,
    ModerationChannelBatch,
    humanize_timestamp,
)
import modcord.moderation.moderation_parsing as moderation_parsing
from modcord.configuration.app_configuration import app_config
from xgrammar.grammar import Grammar

logger = get_logger("ai_moderation_processor")


class ModerationProcessor:
    """Coordinate moderation prompts, inference, and response parsing."""

    def __init__(self, engine: Optional[InferenceProcessor] = None) -> None:
        self.inference_processor = engine or inference_processor
        self._shutdown = False

    # ======== Engine Lifecycle ========
    async def init_model(self, model: Optional[str] = None) -> bool:
        """Initialize the inference engine and report availability."""
        self._shutdown = False
        result = await self.inference_processor.init_model(model)
        if not result:
            logger.warning(
                "init_model: model not available (%s)",
                self.inference_processor.state.init_error,
            )
        return result

    async def start_batch_worker(self) -> bool:
        """Start background worker tasks for batch processing."""
        if not await self._ensure_model_initialized():
            return False
        return True

    # ======== Main Business Logic ========
    async def get_batch_moderation_actions(
        self,
        batch: ModerationChannelBatch,
        server_rules: str = "",
    ) -> List[ActionData]:
        """Process a batch of messages and return moderation actions.
        
        This is the main entry point for batch moderation. It:
        1. Converts batch to JSON format with image IDs
        2. Collects PIL images separately
        3. Formats for vLLM with multimodal content
        4. Generates dynamic schema based on non-history user IDs and their message IDs
        5. Submits to AI model with guided decoding (xgrammar)
        6. Parses response and returns actions
        
        The dynamic schema constrains AI outputs to:
        - Only non-history users (users who sent messages in this batch)
        - Only message IDs belonging to each specific user
        - Valid channel ID and action types
        This prevents hallucination and cross-user message deletion.
        """
        logger.debug(
            "[MODERATION] Processing batch: channel=%s, messages=%d, history=%d",
            batch.channel_id,
            len(batch.messages),
            len(batch.history),
        )
        
        # Get system prompt with rules
        merged_rules = self._resolve_server_rules(server_rules)
        system_prompt = self.inference_processor.get_system_prompt(merged_rules)
        
        # Convert batch to JSON payload with image IDs, collect images
        json_payload, pil_images, _ = self._batch_to_json_with_images(batch)
        
        # Build user->message_ids map for non-history users only
        user_message_map: Dict[str, List[str]] = {}
        for msg in batch.messages:
            user_id = str(msg.user_id)
            if user_id not in user_message_map:
                user_message_map[user_id] = []
            user_message_map[user_id].append(str(msg.message_id))
        
        channel_id = str(batch.channel_id)
        
        # Build dynamic schema with per-user message ID constraints
        dynamic_schema = moderation_parsing.build_dynamic_moderation_schema(user_message_map, channel_id)
        
        # Compile grammar for guided decoding
        grammar = Grammar.from_json_schema(dynamic_schema, strict_mode=True)
        grammar_str = str(grammar)
        
        # Format for vLLM with images
        llm_messages = self._format_multimodal_messages(
            system_prompt,
            json_payload,
            pil_images
        )
        
        logger.info(
            "[INPUT] Submitting batch with %d non-history users, %d images to LLM",
            len(user_message_map),
            len(pil_images)
        )
        
        # Submit to model with guided decoding
        response_text = await self._run_inference(llm_messages, grammar_str)
        logger.info(
            "[MODERATION RAW OUTPUT] Response length: %d chars\n%s",
            len(response_text),
            response_text[:2000],
        )
        
        # Parse response into actions (schema validation guarantees correctness)
        actions = moderation_parsing.parse_batch_actions(
            response_text,
            batch.channel_id,
            dynamic_schema
        )
        logger.info("[MODERATION] Parsed %d actions from response", len(actions))
        
        return actions

    def _batch_to_json_with_images(
        self,
        batch: ModerationChannelBatch,
    ) -> tuple[Dict[str, Any], List[Any], Dict[str, int]]:
        """Convert ModerationChannelBatch to JSON structure with image IDs.
        
        Returns:
            Tuple of (json_payload, pil_images_list, image_id_map)
        """
        all_messages = list(batch.messages) + list(batch.history)
        pil_images: List[Any] = []
        image_id_map: Dict[str, int] = {}
        users_dict: Dict[str, Dict[str, Any]] = {}
        
        # Collect messages and images, group by user
        for msg in all_messages:
            user_id = str(msg.user_id)
            
            # Initialize user dict if first message from this user
            if user_id not in users_dict:
                users_dict[user_id] = {
                    "username": msg.username,
                    "messages": [],
                    "message_count": 0,
                }
            
            # Collect image IDs for this message
            msg_image_ids = []
            for img in msg.images:
                if img.pil_image and img.image_id:
                    if img.image_id not in image_id_map:
                        image_id_map[img.image_id] = len(pil_images)
                        pil_images.append(img.pil_image)
                    msg_image_ids.append(img.image_id)
            
            msg_dict = {
                "message_id": str(msg.message_id),
                "timestamp": humanize_timestamp(msg.timestamp) if msg.timestamp else None,
                "content": msg.content or ("[Images only]" if msg_image_ids else ""),
                "image_ids": msg_image_ids,
                "is_history": msg in batch.history,
            }
            
            users_dict[user_id]["messages"].append(msg_dict)
            users_dict[user_id]["message_count"] = len(users_dict[user_id]["messages"])
        
        payload = {
            "channel_id": str(batch.channel_id),
            "message_count": len(all_messages),
            "unique_user_count": len(users_dict),
            "total_images": len(pil_images),
            "users": users_dict,
        }
        
        return payload, pil_images, image_id_map

    def _format_multimodal_messages(
        self,
        system_prompt: str,
        json_payload: Dict[str, Any],
        pil_images: List[Any]
    ) -> List[Dict[str, Any]]:
        """Build vLLM-compatible messages with multimodal content.
        
        Args:
            system_prompt: The system prompt text
            json_payload: JSON dict with message data and image IDs
            pil_images: List of PIL Image objects
            
        Returns:
            List of vLLM messages with multimodal content
        """
        # Build user message content as list with text + images
        user_content = [
            {
                "type": "text",
                "text": json.dumps(json_payload, indent=2)
            }
        ]
        
        # Add all PIL images
        for pil_img in pil_images:
            user_content.append({
                "type": "image_pil",
                "image_pil": pil_img
            })
        
        logger.debug(
            "[FORMAT_MESSAGES] Built multimodal message: %d text + %d images",
            1,
            len(pil_images)
        )
        
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

    async def _run_inference(
        self,
        messages: List[Dict[str, Any]],
        grammar_str: str
    ) -> str:
        """Submit vLLM-formatted messages to AI model and return raw response string."""
        if self._shutdown:
            logger.warning("[INFERENCE] Processor is shutting down")
            return self._null_response("shutting down")
        
        if not self.inference_processor.is_model_available():
            reason = self.inference_processor.get_model_init_error()
            logger.warning("[INFERENCE] Model not available: %s", reason)
            return self._null_response(reason or "unavailable")
        
        # Generate response with guided decoding
        try:
            logger.info("[INFERENCE] Starting model inference with guided decoding...")
            result = await self.inference_processor.generate_chat(
                messages,
                guided_decoding_grammar=grammar_str
            )
            logger.info(
                "[INFERENCE] Model inference completed, response length: %d chars",
                len(result or "")
            )
            return result.strip() if result else self._null_response("no response")
        except Exception as exc:
            logger.error("[INFERENCE] Inference error: %s", exc, exc_info=True)
            return self._null_response("inference error")

    async def _ensure_model_initialized(self) -> bool:
        """Ensure the model has been initialized at least once."""
        if not self.inference_processor.state.init_started:
            return await self.init_model()
        return True

    def _resolve_server_rules(self, server_rules: str = "") -> str:
        """Pick guild-specific rules when provided, otherwise fall back to global defaults."""
        base_rules = (app_config.server_rules or "").strip()
        guild_rules = (server_rules or "").strip()
        resolved = guild_rules or base_rules
        logger.debug(
            "Resolved server rules: guild_rules_len=%d, base_rules_len=%d, using=%s",
            len(guild_rules),
            len(base_rules),
            "guild" if guild_rules else "base"
        )
        return resolved

    async def shutdown(self) -> None:
        """Gracefully stop the moderation processor and unload the AI model."""
        if self._shutdown:
            logger.debug("ModerationProcessor.shutdown called multiple times")
            return

        self._shutdown = True

        try:
            await self.inference_processor.unload_model()
        except Exception as exc:
            logger.warning("Failed to unload AI model cleanly: %s", exc)

    @staticmethod
    def _null_response(reason: str) -> str:
        return f"null: {reason}"


# Module-level instances
moderation_processor = ModerationProcessor()
model_state = inference_processor.state


# Direct API functions (eliminates ai_lifecycle abstraction layer)
async def initialize_engine(model: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """Initialize the moderation engine. Returns (success, error_message)."""
    logger.info("[ENGINE] Initializing moderation engine...")
    await moderation_processor.init_model(model)
    await moderation_processor.start_batch_worker()
    return model_state.available, model_state.init_error


async def restart_engine(model: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """Restart the moderation engine. Returns (success, error_message)."""
    logger.info("[ENGINE] Restarting moderation engine...")
    try:
        await moderation_processor.shutdown()
    except Exception as exc:
        logger.warning("[ENGINE] Shutdown during restart failed: %s", exc)

    model_state.available = False
    model_state.init_error = None

    await moderation_processor.init_model(model)
    await moderation_processor.start_batch_worker()
    return model_state.available, model_state.init_error


async def shutdown_engine() -> None:
    """Shutdown the moderation engine."""
    logger.info("[ENGINE] Shutting down moderation engine...")
    await moderation_processor.shutdown()
