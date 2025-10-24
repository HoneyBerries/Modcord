"""High-level orchestration logic for AI-driven moderation workflows.

This module coordinates the entire moderation pipeline, including:
- Converting channel batches into vLLM-compatible conversations.
- Dynamically building JSON schemas and guided decoding grammars for each channel.
- Submitting all conversations in a single batch to the AI model for inference.
- Parsing responses and applying moderation actions per channel.

Key Features:
- Supports multimodal inputs (text + images).
- Handles per-channel server rules dynamically.
- Ensures efficient batch processing for high throughput.
"""

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
    """
    Coordinate moderation prompts, inference, and response parsing.

    This class manages the lifecycle of the moderation engine, including:
    - Initializing the AI model and ensuring availability.
    - Converting channel batches into vLLM-compatible inputs.
    - Dynamically generating JSON schemas and grammars for guided decoding.
    - Submitting all conversations in a single batch to the AI model.
    - Parsing responses and grouping actions by channel.

    Attributes:
        inference_processor (InferenceProcessor): The AI inference engine.
        _shutdown (bool): Tracks whether the processor is shutting down.
    """

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
    async def get_multi_batch_moderation_actions(
        self,
        batches: List[ModerationChannelBatch],
        server_rules_map: Optional[Dict[int, str]] = None,
        channel_guidelines_map: Optional[Dict[int, str]] = None,
    ) -> Dict[int, List[ActionData]]:
        """
        Process multiple channel batches in a single global inference call.

        This is the global batch processing entry point. It:
        1. Converts all batches to vLLM conversations (one per channel).
        2. Dynamically builds JSON schemas and guided decoding grammars for each channel.
        3. Submits all conversations to vLLM in one call for efficient inference.
        4. Parses responses and groups actions by channel.

        Args:
            batches: List of ModerationChannelBatch objects from different channels.
            server_rules_map: Optional mapping of channel_id -> server rules text.
            channel_guidelines_map: Optional mapping of channel_id -> channel-specific guidelines text.

        Returns:
            Dictionary mapping channel_id to list of ActionData objects.
        """
        logger.debug(
            "[MODERATION] Processing global batch: %d channels",
            len(batches)
        )

        if not batches:
            return {}
        
        # Build conversations for each channel batch
        conversations = []
        grammar_strings: List[str] = []
        channel_mapping = []  # Maps conversation index to channel_id and batch
        rules_lookup = server_rules_map or {}
        guidelines_lookup = channel_guidelines_map or {}

        for batch in batches:
            # Convert batch to JSON payload with image IDs
            json_payload, pil_images, _ = self._batch_to_json_with_images(batch)

            # Build user->message_ids map for non-history users
            user_message_map: Dict[str, List[str]] = {}
            for msg in batch.messages:
                user_id = str(msg.user_id)
                if user_id not in user_message_map:
                    user_message_map[user_id] = []
                user_message_map[user_id].append(str(msg.message_id))

            channel_id_str = str(batch.channel_id)

            # Build dynamic schema for this batch
            dynamic_schema = moderation_parsing.build_dynamic_moderation_schema(
                user_message_map, channel_id_str
            )

            # Compile grammar for guided decoding
            grammar = Grammar.from_json_schema(dynamic_schema, strict_mode=True)
            grammar_str = str(grammar)

            # Resolve and apply server rules and channel guidelines per channel
            channel_rules = rules_lookup.get(batch.channel_id, "")
            merged_rules = self._resolve_server_rules(channel_rules)
            
            channel_guidelines = guidelines_lookup.get(batch.channel_id, "")
            merged_guidelines = self._resolve_channel_guidelines(channel_guidelines)
            
            system_prompt = self.inference_processor.get_system_prompt(merged_rules, merged_guidelines)

            # Format messages for vLLM
            llm_messages = self._format_multimodal_messages(
                system_prompt,
                json_payload,
                pil_images
            )

            conversations.append(llm_messages)
            grammar_strings.append(grammar_str)
            channel_mapping.append((batch.channel_id, batch, dynamic_schema))

            logger.debug(
                "[BATCH_PREP] Channel %d: %d users, %d images",
                batch.channel_id,
                len(user_message_map),
                len(pil_images)
            )

        logger.debug(
            "[INPUT] Submitting global batch with %d channels/conversations to LLM",
            len(conversations)
        )
        
        # Submit all conversations to vLLM in one call
        responses = await self._run_multi_inference(conversations, grammar_strings)

        if len(responses) != len(channel_mapping):
            logger.warning(
                "[MODERATION] Response count mismatch: %d responses for %d channels",
                len(responses),
                len(channel_mapping),
            )

        # Parse responses and group actions by channel
        actions_by_channel: Dict[int, List[ActionData]] = {}
        for (channel_id, _, dynamic_schema), response_text in zip(channel_mapping, responses):
            
            logger.debug(
                "[MODERATION RAW OUTPUT] Channel %d response length: %d chars\n%s",
                channel_id,
                len(response_text),
                response_text[:2000],
            )
            
            # Parse response into actions
            actions = moderation_parsing.parse_batch_actions(
                response_text,
                channel_id,
                dynamic_schema
            )
            actions_by_channel[channel_id] = actions
            logger.debug(
                "[MODERATION] Parsed %d actions for channel %d",
                len(actions),
                channel_id
            )
        
        if len(channel_mapping) > len(responses):
            for channel_id, _, _ in channel_mapping[len(responses):]:
                logger.warning("[MODERATION] Missing response for channel %d", channel_id)
                actions_by_channel.setdefault(channel_id, [])

        return actions_by_channel

    def _batch_to_json_with_images(
        self,
        batch: ModerationChannelBatch,
    ) -> tuple[Dict[str, Any], List[Any], Dict[str, int]]:
        """
        Convert ModerationChannelBatch to JSON structure with image IDs.

        This method processes all messages and history in the batch, grouping them by user
        and collecting associated image IDs. The resulting JSON payload is used as input
        for the AI model.

        Returns:
            Tuple of (json_payload, pil_images_list, image_id_map).
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
        """
        Build vLLM-compatible messages with multimodal content.

        Args:
            system_prompt: The system prompt text.
            json_payload: JSON dict with message data and image IDs.
            pil_images: List of PIL Image objects.

        Returns:
            List of vLLM messages with multimodal content.
        """
        # Build user message content as list with text + images
        user_content = [
            {
                "type": "text",
                "text": json.dumps(json_payload, separators=(",", ":"))
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

    async def _run_multi_inference(
        self,
        conversations: List[List[Dict[str, Any]]],
        grammar_strings: List[str]
    ) -> List[str]:
        """
        Submit multiple vLLM-formatted conversations to AI model and return responses.

        This method processes multiple conversations in a single vLLM call for efficiency.

        Args:
            conversations: List of conversation message lists (one per channel).
            grammar_strings: List of grammar strings (one per conversation).

        Returns:
            List of response strings (one per conversation).
        """
        if self._shutdown:
            logger.warning("[INFERENCE] Processor is shutting down")
            return [self._null_response("shutting down") for _ in conversations]
        
        if not self.inference_processor.is_model_available():
            reason = self.inference_processor.get_model_init_error()
            logger.warning("[INFERENCE] Model not available: %s", reason)
            return [self._null_response(reason or "unavailable") for _ in conversations]
        
        try:
            logger.debug("[INFERENCE] Starting multi-batch inference with %d conversations...", len(conversations))
            results = await self.inference_processor.generate_multi_chat(
                conversations,
                grammar_strings
            )
            logger.debug(
                "[INFERENCE] Multi-batch inference completed, %d responses",
                len(results)
            )
            return [r.strip() if r else self._null_response("no response") for r in results]
        except Exception as exc:
            logger.error("[INFERENCE] Multi-batch inference error: %s", exc, exc_info=True)
            return [self._null_response("inference error") for _ in conversations]

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

    def _resolve_channel_guidelines(self, channel_guidelines: str = "") -> str:
        """Pick channel-specific guidelines when provided, otherwise fall back to global defaults."""
        base_guidelines = (app_config.channel_guidelines or "").strip()
        channel_specific = (channel_guidelines or "").strip()
        resolved = channel_specific or base_guidelines
        logger.debug(
            "Resolved channel guidelines: channel_specific_len=%d, base_guidelines_len=%d, using=%s",
            len(channel_specific),
            len(base_guidelines),
            "channel_specific" if channel_specific else "base"
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
