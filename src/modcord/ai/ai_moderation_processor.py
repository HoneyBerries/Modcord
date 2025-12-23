"""High-level orchestration logic for AI-driven moderation workflows.

This module coordinates the entire moderation pipeline using an OpenAI-compatible API:
- Converting channel batches into chat completion requests with multimodal content.
- Dynamically building JSON schemas for structured outputs.
- Submitting concurrent requests to the API using asyncio.gather().
- Parsing responses and applying moderation actions per channel.

Key Features:
- Uses AsyncOpenAI client for inference (compatible with vLLM, LM Studio, etc.).
- Supports multimodal inputs (text + images via URLs).
- Handles per-channel server rules dynamically.
- Ensures efficient concurrent processing for high throughput.
"""

from __future__ import annotations

import asyncio
import json

from typing import Any, Dict, List, Tuple
from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionContentPartParam,
    ChatCompletionContentPartImageParam,
    ChatCompletionContentPartTextParam,
)
from openai.types.shared_params.response_format_json_schema import ResponseFormatJSONSchema

from modcord.util.logger import get_logger
from modcord.datatypes.action_datatypes import ActionData
from modcord.datatypes.moderation_datatypes import ModerationChannelBatch
from modcord.datatypes.discord_datatypes import UserID, MessageID, ChannelID, GuildID
from modcord.moderation import moderation_parsing
from modcord.configuration.app_configuration import app_config
from modcord.settings.guild_settings_manager import guild_settings_manager



logger = get_logger("ai_moderation_processor")

class ModerationProcessor:
    """
    Coordinate moderation prompts, inference, and response parsing.

    This class manages the moderation pipeline using an OpenAI-compatible API:
    - Initializing the AsyncOpenAI client from configuration.
    - Converting channel batches into chat completion requests.
    - Dynamically generating JSON schemas for structured outputs.
    - Submitting concurrent requests using asyncio.gather().
    - Parsing responses and grouping actions by channel.
    """

    def __init__(self) -> None:
        """Initialize the ModerationProcessor with AsyncOpenAI client."""
        ai_settings = app_config.ai_settings
        self._client = AsyncOpenAI(
            api_key=ai_settings.api_key,
            base_url=ai_settings.base_url,
        )
        self._model_name = ai_settings.model_name
        self._base_system_prompt = app_config.system_prompt_template
        logger.info(
            "[MODERATION] Initialized with base_url=%s, model=%s",
            ai_settings.base_url,
            self._model_name,
        )

    def generate_dynamic_system_prompt(self, guild_id: GuildID, channel_id: ChannelID) -> str:
        """Build the system prompt with guild-specific and channel-specific rules and guidelines.

        This method handles all the logic for resolving and injecting rules and guidelines:
        1. Fetches guild settings and channel guidelines from guild_settings_manager.
        2. Falls back to global defaults if guild/channel-specific settings are not set.
        3. Injects them into the system prompt template.

        Args:
            guild_id: The guild ID to fetch rules from.
            channel_id: The channel ID to fetch channel-specific guidelines from.

        Returns:
            Formatted system prompt string with injected rules and guidelines.
        """
        template = self._base_system_prompt or ""
        settings = guild_settings_manager.get(guild_id)
        
        guild_rules = (settings.rules or "").strip() or (app_config.server_rules or "").strip()
        channel_guidelines = (settings.channel_guidelines.get(channel_id, "") or "").strip() or (app_config.channel_guidelines or "").strip()
        
        # Inject into template
        template = template.replace("<|SERVER_RULES_INJECT|>", guild_rules) if guild_rules else template
        template = template.replace("<|CHANNEL_GUIDELINES_INJECT|>", channel_guidelines) if channel_guidelines else template
        
        if guild_rules and "<|SERVER_RULES_INJECT|>" not in self._base_system_prompt:
            template += f"\n\nServer rules:\n{guild_rules}"
        if channel_guidelines and "<|CHANNEL_GUIDELINES_INJECT|>" not in self._base_system_prompt:
            template += f"\n\nChannel-specific guidelines:\n{channel_guidelines}"
        
        return template

    async def get_multi_batch_moderation_actions(
        self,
        batches: List[ModerationChannelBatch]) -> Dict[int, List[ActionData]]:
        """
        Process multiple channel batches using concurrent API requests.

        This is the main entry point for batch moderation. It:
        1. Converts all batches to chat completion requests (one per channel).
        2. Dynamically builds JSON schemas for structured outputs per channel.
        3. Submits all requests concurrently using asyncio.gather() to the OpenAI API.
        4. Parses responses and groups actions by channel.

        Args:
            batches: List of ModerationChannelBatch objects. Each batch includes its own guild_id.
            guild_id: (Optional) Fallback guild_id if a batch's guild_id is not set.

        Returns:
            Dictionary mapping channel_id (as int) to list of ActionData objects.
        """
        logger.debug("[MODERATION] Processing batch: %d channels", len(batches))

        if not batches:
            return {}

        # Prepare all requests
        request_data: List[
            Tuple[
                ChannelID,
                ModerationChannelBatch,
                Dict[str, Any],
                List[ChatCompletionMessageParam],
                ResponseFormatJSONSchema,
            ]
        ] = []

        for batch in batches:
            # Convert batch to JSON payload with image IDs
            json_payload, image_urls, image_id_map = batch.convert_batch_to_mm_llm_payload()

            # Build user->message_ids map for non-history users
            user_message_map: Dict[UserID, List[MessageID]] = {}
            for user in batch.users:
                user_message_map[user.user_id] = [msg.message_id for msg in user.messages]

            # Build dynamic schema for this batch
            dynamic_schema = moderation_parsing.build_dynamic_moderation_schema(
                user_message_map, batch.channel_id
            )

            # Build system prompt with resolved rules and guidelines
            system_prompt = self.generate_dynamic_system_prompt(batch.guild_id, batch.channel_id)

            # Build OpenAI messages directly from the batch payload
            user_content: List[ChatCompletionContentPartParam] = [
                ChatCompletionContentPartTextParam(
                    type="text",
                    text=json.dumps(json_payload, separators=(",", ":"))
                )
            ]

            # Use hashed image IDs (already in payload) and map to URLs
            for image_id, idx in sorted(image_id_map.items()):
                if idx < len(image_urls):
                    user_content.append(
                        ChatCompletionContentPartTextParam(
                            type="text",
                            text=f"Image (ID: {image_id}):"
                        )
                    )
                    user_content.append(
                        ChatCompletionContentPartImageParam(
                            type="image_url",
                            image_url={"url": image_urls[idx]}
                        )
                    )

            messages: List[ChatCompletionMessageParam] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]

            # Convert schema to OpenAI format
            response_format = ResponseFormatJSONSchema(
                type="json_schema",
                json_schema={
                    "name": "moderation_response",
                    "strict": True,
                    "schema": dynamic_schema
                }
            )

            request_data.append((batch.channel_id, batch, dynamic_schema, messages, response_format))


        # Submit all requests concurrently
        async def make_concurrent_request(
                channel_id: ChannelID,
                messages: List[ChatCompletionMessageParam],
                response_format: ResponseFormatJSONSchema
            ) -> Tuple[ChannelID, str]:
                """Make a single API request and return the response."""
                try:
                    response = await self._client.chat.completions.create(
                        model=self._model_name,
                        messages=messages,
                        response_format=response_format,
                    )
                    content = response.choices[0].message.content or ""
                    return (channel_id, content.strip())
                except Exception as exc:
                    logger.error("[MODERATION] API request failed for channel %s: %s", channel_id, exc)
                    return (channel_id, self._null_response(str(exc)))

        # Create tasks for all requests
        tasks = [
            make_concurrent_request(channel_id, messages, response_format)
            for channel_id, _, _, messages, response_format in request_data
        ]

        # Run all requests concurrently
        results = await asyncio.gather(*tasks)

        # Build response lookup
        response_lookup: Dict[ChannelID, str] = {channel_id: response for channel_id, response in results}

        # Parse responses and group actions by channel
        actions_by_channel: Dict[int, List[ActionData]] = {}
        for channel_id, batch, dynamic_schema, _, _ in request_data:
            response_text = response_lookup.get(channel_id, self._null_response("no response"))

            # Parse response into actions using batch's guild_id
            actions = moderation_parsing.parse_batch_actions(
                response_text,
                channel_id,
                batch.guild_id,
                dynamic_schema
            )
            actions_by_channel[channel_id.to_int()] = actions

            # Log summary
            action_summary = ", ".join(f"{a.action}({a.user_id})" for a in actions if a.action != "null")
            logger.debug(
                "[RESULT] Channel %s: %d actions [%s] | Response: \n%s",
                channel_id,
                len([a for a in actions if a.action != "null"]),
                action_summary or "none",
                response_text
            )

        return actions_by_channel


    @staticmethod
    def _null_response(reason: str) -> str:
        """Return a null response string for error cases."""
        return f"null: {reason}"


# Module-level instance
moderation_processor = ModerationProcessor()