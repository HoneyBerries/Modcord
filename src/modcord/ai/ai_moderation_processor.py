"""High-level orchestration logic for AI-driven moderation workflows."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from modcord.ai.ai_core import InferenceProcessor, inference_processor
from modcord.util.logger import get_logger
from modcord.util.moderation_datatypes import (
    ActionData,
    ActionType,
    ModerationBatch,
    ModerationMessage,
    humanize_timestamp,
)
import modcord.util.moderation_parsing as moderation_parsing
from modcord.configuration.app_configuration import app_config


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
        await self.inference_processor.init_model(model)
        available = bool(self.inference_processor.state.available)
        if not available:
            logger.warning(
                "init_model: model not available (%s)",
                self.inference_processor.state.init_error,
            )
        return available

    async def start_batch_worker(self) -> bool:
        """Start background worker tasks for batch processing."""
        if not await self._ensure_model_initialized():
            return False
        return True

    # ======== Main Business Logic ========
    async def get_batch_moderation_actions(
        self,
        batch: ModerationBatch,
        server_rules: str = "",
    ) -> List[ActionData]:
        """Process a batch of messages and return moderation actions.
        
        This is the main entry point for batch moderation. It:
        1. Converts batch to JSON format
        2. Formats for vLLM with multimodal content
        3. Submits to AI model
        4. Parses and returns actions
        """
        # Get system prompt with rules
        merged_rules = self._resolve_server_rules(server_rules)
        system_prompt = await self.inference_processor.get_system_prompt(merged_rules)
        
        # Convert batch to JSON payload (keeping images separate)
        json_payload, images = self._batch_to_json(batch)
        
        # Format for vLLM with images
        llm_messages = await self._format_multimodal_messages(system_prompt, json_payload, images)
        
        # Submit to model
        response_text = await self._run_inference(llm_messages)
        
        # Parse response
        parsed_actions = await moderation_parsing.parse_batch_actions(response_text, batch.channel_id)
        
        # Simple reconciliation - just match user IDs
        return self._reconcile_actions(parsed_actions, batch)

    def _batch_to_json(self, batch: ModerationBatch) -> tuple[Dict[str, Any], List[Any]]:
        """Convert ModerationBatch to JSON structure for the LLM.
        
        Returns (json_payload, images_list) where:
        - json_payload: JSON-serializable dict with message data (NO PIL images)
        - images_list: List of PIL Image objects to pass separately to vLLM
        """
        # Combine messages and history
        all_messages = list(batch.messages) + list(batch.history)
        
        # Group by user and collect images separately
        users_dict: Dict[str, Dict[str, Any]] = {}
        images_list: List[Any] = []
        
        for msg in all_messages:
            user_id = str(msg.user_id)
            if user_id not in users_dict:
                users_dict[user_id] = {
                    "username": msg.username,
                    "messages": [],
                    "message_count": 0,
                }
            
            # Build message dict WITHOUT PIL images (just metadata)
            msg_dict = {
                "message_id": str(msg.message_id),
                "timestamp": humanize_timestamp(msg.timestamp) if msg.timestamp else None,
                "content": msg.content or ("[Image attachment]" if msg.images else ""),
                "images": [
                    {
                        "attachment_id": img.attachment_id,
                        "message_id": img.message_id,
                        "user_id": img.user_id,
                        "filename": img.filename,
                    }
                    for img in msg.images
                ],
                "is_history": msg in batch.history,
            }
            
            # Collect PIL images separately for vLLM
            for img in msg.images:
                if img.pil_image:
                    images_list.append(img.pil_image)
            
            users_dict[user_id]["messages"].append(msg_dict)
            users_dict[user_id]["message_count"] = len(users_dict[user_id]["messages"])
        
        payload = {
            "channel_id": str(batch.channel_id),
            "message_count": len(all_messages),
            "unique_user_count": len(users_dict),
            "users": users_dict,
        }
        
        return payload, images_list

    async def _run_inference(self, messages: List[Dict[str, Any]]) -> str:
        """Submit vLLM-formatted messages to AI model and return raw response string."""
        # Check model availability
        if self._shutdown:
            return self._null_response("shutting down")
        
        ok, reason = await self._ensure_model_available()
        if not ok:
            return self._null_response(reason)
        
        # Generate response
        try:
            result = await self.inference_processor.generate_chat(messages)
            return result.strip() if result else self._null_response("no response")
        except Exception as exc:
            logger.error("Inference error: %s", exc)
            return self._null_response("inference error")

    # ======== Helpers: Engine ========
    async def _ensure_model_initialized(self) -> bool:
        """Ensure the model has been initialized at least once."""
        if not self.inference_processor.state.init_started:
            return await self.init_model()
        return True


    async def _ensure_model_available(self) -> tuple[bool, str]:
        """Check model availability and return (ok, reason_if_not_ok)."""
        await self.inference_processor.get_model()
        state = self.inference_processor.state
        ready = (
            state.available
            and self.inference_processor.engine is not None
            and self.inference_processor.sampling_params is not None
        )
        return (True, "") if ready else (False, state.init_error or "AI model unavailable")

    # ======== Multimodal Content Formatting ========
    async def _format_multimodal_messages(
        self, 
        system_prompt: str, 
        json_payload: Dict[str, Any], 
        images: List[Any]
    ) -> List[Dict[str, Any]]:
        """Build vLLM-compatible messages with multimodal content.
        
        Args:
            system_prompt: The system prompt text
            json_payload: JSON-serializable dict (no PIL images)
            images: List of PIL Image objects
            
        Returns:
            List of vLLM messages with proper content format
        """
        # Build text content from JSON payload
        text_parts = []
        
        # Add channel info
        if "channel_id" in json_payload:
            text_parts.append(f"Channel: {json_payload['channel_id']}")
        
        # Process users and their messages
        for user_id, user_data in json_payload.get("users", {}).items():
            username = user_data.get("username", f"user_{user_id}")
            text_parts.append(f"\n\nUser: {username} (ID: {user_id})")
            text_parts.append(f"Message count: {user_data.get('message_count', 0)}")
            
            for msg_data in user_data.get("messages", []):
                text_parts.append(f"\nMessage ID: {msg_data.get('message_id')}")
                if msg_data.get("timestamp"):
                    text_parts.append(f"Time: {msg_data['timestamp']}")
                text_parts.append(f"Content: {msg_data.get('content', '')}")
                
                # Add image metadata (but not the actual images)
                for img_idx, img_data in enumerate(msg_data.get("images", [])):
                    filename = img_data.get("filename", "image")
                    text_parts.append(
                        f"[Image {img_idx + 1}: {filename} "
                        f"from message {img_data.get('message_id')} "
                        f"by user {img_data.get('user_id')}]"
                    )
        
        # Build vLLM content format: text first, then images
        # According to vLLM docs, content is a list of items
        user_content = [{"type": "text", "text": "\n".join(text_parts)}]
        
        # Add PIL images in vLLM format
        for pil_img in images:
            user_content.append({"type": "image_pil", "image_pil": pil_img})
        
        # Return vLLM messages
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

    def _resolve_server_rules(self, server_rules: str = "") -> str:
        """Pick guild-specific rules when provided, otherwise fall back to global defaults."""
        base_rules = (app_config.server_rules or "").strip()
        guild_rules = (server_rules or "").strip()
        resolved = guild_rules or base_rules
        logger.debug("Resolved server rules: guild_rules_len=%d, base_rules_len=%d, using=%s", 
                     len(guild_rules), len(base_rules), "guild" if guild_rules else "base")
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

    def _reconcile_actions(
        self,
        parsed_actions: List[ActionData],
        batch: ModerationBatch,
    ) -> List[ActionData]:
        """Reconcile AI-generated actions with actual messages in the batch.
        
        Simplified version that just validates user IDs and message IDs exist in the batch.
        """
        # Build lookup maps from batch
        all_messages = list(batch.messages) + list(batch.history)
        user_messages: Dict[str, List[ModerationMessage]] = {}
        
        for msg in all_messages:
            user_id = str(msg.user_id)
            if user_id not in user_messages:
                user_messages[user_id] = []
            user_messages[user_id].append(msg)
        
        final_actions: List[ActionData] = []
        
        for action in parsed_actions:
            user_id = action.user_id.strip()
            if not user_id:
                continue
            
            # Get messages for this user
            user_msgs = user_messages.get(user_id, [])
            if not user_msgs:
                logger.debug(f"User {user_id} from AI response not in batch, skipping")
                continue
            
            # Validate message IDs
            valid_msg_ids = {str(msg.message_id) for msg in user_msgs}
            ai_msg_ids = [mid.strip() for mid in action.message_ids if mid]
            validated_msg_ids = [mid for mid in ai_msg_ids if mid in valid_msg_ids]
            
            # If AI specified message IDs but none are valid, use all user's message IDs
            if ai_msg_ids and not validated_msg_ids:
                validated_msg_ids = list(valid_msg_ids)
            elif not validated_msg_ids:
                validated_msg_ids = list(valid_msg_ids)
            
            # Downgrade actions that require message IDs if we don't have any
            action_type = action.action
            if action_type in {ActionType.DELETE, ActionType.KICK, ActionType.BAN, ActionType.TIMEOUT}:
                if not validated_msg_ids:
                    logger.debug(f"No message IDs for {action_type.value} action on user {user_id}, downgrading")
                    action_type = ActionType.WARN if action_type != ActionType.DELETE else ActionType.NULL
            
            final_actions.append(
                ActionData(
                    user_id=user_id,
                    action=action_type,
                    reason=action.reason or "Automated moderation action",
                    message_ids=validated_msg_ids,
                    timeout_duration=action.timeout_duration if action_type == ActionType.TIMEOUT else None,
                    ban_duration=action.ban_duration if action_type == ActionType.BAN else None,
                )
            )
        
        return final_actions

    @staticmethod
    def _null_response(reason: str) -> str:
        return f"null: {reason}"


moderation_processor = ModerationProcessor()
model_state = inference_processor.state