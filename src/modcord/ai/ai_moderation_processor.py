"""High-level orchestration logic for AI-driven moderation workflows."""

from __future__ import annotations

import json
import traceback
import asyncio
from io import BytesIO
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
        # Run synchronous init in executor to not block asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self.inference_processor.init_model, model)
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
        1. Downloads and converts images to PIL format
        2. Converts batch to multimodal format with PIL images
        3. Submits to AI model using llm.chat()
        4. Parses and returns actions
        """
        logger.debug(
            "[MODERATION] Processing batch: channel=%s, messages=%d, history=%d",
            batch.channel_id,
            len(batch.messages),
            len(batch.history),
        )
        
        # Download and convert images to PIL
        await self._download_images(batch)
        
        # Get system prompt with rules
        merged_rules = self._resolve_server_rules(server_rules)
        system_prompt = self.inference_processor.get_system_prompt(merged_rules)
        
        # Build multimodal messages with PIL images
        llm_messages, user_ids = self._build_multimodal_messages(system_prompt, batch)
        
        # Log the formatted message info
        logger.info(
            "[INPUT] messages=%d, users=%d, images=%d",
            len(batch.messages) + len(batch.history),
            len(user_ids),
            sum(len(msg.images) for msg in batch.messages + batch.history)
        )
        
        # Submit to model using llm.chat()
        response_text = await self._run_inference(llm_messages, user_ids, str(batch.channel_id))
        logger.info(
            "[MODERATION RAW OUTPUT] Response length: %d chars\n%s",
            len(response_text),
            response_text[:2000],
        )
        
        # Parse response
        parsed_actions = await moderation_parsing.parse_batch_actions(response_text, batch.channel_id)
        logger.info(
            "[MODERATION] Parsed actions: %d actions from response",
            len(parsed_actions),
        )
        for idx, action in enumerate(parsed_actions):
            logger.debug(
                "[MODERATION] Action %d: user=%s, action=%s, reason=%s, msg_ids=%s",
                idx,
                action.user_id,
                action.action.value if hasattr(action.action, 'value') else str(action.action),
                action.reason[:50] if action.reason else None,
                action.message_ids,
            )
        
        # Simple reconciliation - just match user IDs
        final_actions = self._reconcile_actions(parsed_actions, batch)
        logger.info(
            "[MODERATION] Final reconciled actions: %d actions after reconciliation",
            len(final_actions),
        )
        
        return final_actions

    async def _download_images(self, batch: ModerationBatch) -> None:
        """Download and convert images to PIL format like test_multi_image.py.
        
        Downloads images from URLs and converts them to RGB PIL images.
        """
        import aiohttp
        from PIL import Image
        
        all_messages = list(batch.messages) + list(batch.history)
        
        async def download_image(url: str) -> Optional[Any]:
            """Download an image and convert to PIL RGB."""
            try:
                logger.debug("[DOWNLOAD] %s", url)
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            img = Image.open(BytesIO(data)).convert("RGB")
                            logger.debug("[DOWNLOAD] got size=%s", img.size)
                            return img
                        else:
                            logger.warning("[DOWNLOAD] Failed with status %d", resp.status)
                            return None
            except Exception as exc:
                logger.warning("[DOWNLOAD] Failed to download image: %s", exc)
                return None
        
        # Download all images in parallel
        for msg in all_messages:
            for img_data in msg.images:
                if img_data.source_url and not img_data.pil_image:
                    img_data.pil_image = await download_image(img_data.source_url)

    def _build_multimodal_messages(
        self, 
        system_prompt: str, 
        batch: ModerationBatch
    ) -> tuple[List[Dict[str, Any]], List[str]]:
        """Build vLLM-compatible messages with PIL images like test_multi_image.py.
        
        Returns:
            Tuple of (messages, user_ids) where messages contain text and image_pil content
        """
        all_messages = list(batch.messages) + list(batch.history)
        
        # Group by user
        users_dict: Dict[str, Dict[str, Any]] = {}
        
        for msg in all_messages:
            user_id = str(msg.user_id)
            if user_id not in users_dict:
                users_dict[user_id] = {
                    "username": msg.username,
                    "messages": [],
                }
            
            # Build message dict
            msg_dict = {
                "message_id": str(msg.message_id),
                "timestamp": humanize_timestamp(msg.timestamp) if msg.timestamp else None,
                "content": msg.content or ("[Image attachment]" if msg.images else ""),
                "has_images": len(msg.images) > 0,
                "image_count": len(msg.images),
                "is_history": msg in batch.history,
            }
            
            users_dict[user_id]["messages"].append(msg_dict)
        
        # Build JSON payload
        payload = {
            "channel_id": str(batch.channel_id),
            "message_count": len(all_messages),
            "unique_user_count": len(users_dict),
            "users": users_dict,
        }
        
        # Build multimodal content list
        contents = [
            {"type": "text", "text": json.dumps(payload, indent=2)}
        ]
        
        # Add PIL images
        for msg in all_messages:
            for img_data in msg.images:
                if img_data.pil_image:
                    contents.append({"type": "image_pil", "image_pil": img_data.pil_image})
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": contents},
        ]
        
        user_ids = list(users_dict.keys())
        return messages, user_ids

    async def _run_inference(self, messages: List[Dict[str, Any]], user_ids: List[str], channel_id: str) -> str:
        """Submit vLLM-formatted messages to AI model and return raw response string."""
        # Check model availability
        if self._shutdown:
            logger.warning("[INFERENCE] Processor is shutting down")
            return self._null_response("shutting down")
        
        ok, reason = await self._ensure_model_available()
        if not ok:
            logger.warning("[INFERENCE] Model not available: %s", reason)
            return self._null_response(reason)
        
        # Log the messages being submitted
        logger.debug("[INFERENCE] Submitting %d messages to model", len(messages))
        
        # Generate response using synchronous llm.chat() in executor
        try:
            logger.info("[INFERENCE] Starting model inference call...")
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self.inference_processor.generate_chat,
                messages,
                user_ids,
                channel_id
            )
            logger.info("[INFERENCE] Model inference completed, response length: %d chars", len(result or ""))
            return result.strip() if result else self._null_response("no response")
        except Exception as exc:
            logger.error("[INFERENCE] Inference error: %s\n%s", exc, traceback.format_exc())
            return self._null_response("inference error")

    # ======== Helpers: Engine ========
    async def _ensure_model_initialized(self) -> bool:
        """Ensure the model has been initialized at least once."""
        if not self.inference_processor.state.init_started:
            return await self.init_model()
        return True


    async def _ensure_model_available(self) -> tuple[bool, str]:
        """Check model availability and return (ok, reason_if_not_ok)."""
        loop = asyncio.get_event_loop()
        available = await loop.run_in_executor(None, self.inference_processor.get_model)
        state = self.inference_processor.state
        ready = (
            state.available
            and self.inference_processor.llm is not None
            and self.inference_processor.sampling_params is not None
        )
        return (True, "") if ready else (False, state.init_error or "AI model unavailable")

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
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.inference_processor.unload_model)
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