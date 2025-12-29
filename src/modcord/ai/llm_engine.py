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
from dataclasses import dataclass

from typing import Any, Dict, List
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from openai.types.shared_params.response_format_json_schema import ResponseFormatJSONSchema
import json

from modcord.util.logger import get_logger
from modcord.datatypes.action_datatypes import ActionData
from modcord.datatypes.moderation_datatypes import ModerationChannelBatch
from modcord.moderation import moderation_parsing
from modcord.moderation.moderation_serialization import convert_batch_to_openai_messages
from modcord.datatypes.discord_datatypes import ChannelID, GuildID
from modcord.configuration.app_configuration import app_config
from modcord.settings.guild_settings_manager import guild_settings_manager



logger = get_logger("llm_engine")


@dataclass
class ChannelBatchRequest:
    """Container for a single channel batch's API request data."""
    channel_id: ChannelID
    guild_id: GuildID
    messages: List[ChatCompletionMessageParam]
    response_format: ResponseFormatJSONSchema
    schema: Dict[str, Any]


class LLMEngine:
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
        """Initialize the LLMEngine with AsyncOpenAI client."""
        ai_settings = app_config.ai_settings
        self._client = AsyncOpenAI(
            api_key=ai_settings.api_key,
            base_url=ai_settings.base_url,
        )
        self._model_name = ai_settings.model_name
        self._base_system_prompt = app_config.system_prompt_template
        logger.info(
            "[LLM ENGINE] Initialized with base_url=%s, model=%s",
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
        # Fetch base template
        template = self._base_system_prompt or ""

        # Resolve guild rules and channel guidelines
        settings = guild_settings_manager.get(guild_id)

        guild_rules = (settings.rules or app_config.server_rules).strip()
        channel_guidelines = settings.channel_guidelines.get(channel_id, app_config.channel_guidelines).strip()

        # Inject into template
        prompt = template.replace("<|SERVER_RULES_INJECT|>", guild_rules)
        prompt = prompt.replace("<|CHANNEL_GUIDELINES_INJECT|>", channel_guidelines)

        return prompt



    async def get_moderation_actions(
        self,
        batches: List[ModerationChannelBatch]) -> Dict[int, List[ActionData]]:
        """
        Get moderation actions from AI for multiple batches.

        This method only handles AI inference:
        1. Converts batches to API requests with dynamic schemas
        2. Submits concurrent requests to OpenAI-compatible API
        3. Parses responses into ActionData objects

        Args:
            batches: List of ModerationChannelBatch objects to analyze.

        Returns:
            Dictionary mapping channel_id (as int) to list of ActionData objects.
        """
        logger.debug("[MODERATION] Processing %d batches", len(batches))

        if not batches:
            return {}

        # Prepare all requests
        requests: List[ChannelBatchRequest] = []
        
        for batch in batches:
            # Build system prompt with resolved rules and guidelines
            system_prompt = self.generate_dynamic_system_prompt(batch.guild_id, batch.channel_id)
            
            # Convert batch to OpenAI messages with dynamic schema (single call)
            messages, dynamic_schema = convert_batch_to_openai_messages(batch, system_prompt)

            # Convert dynamic output schema to OpenAI-compatible format
            response_format = ResponseFormatJSONSchema(
                type="json_schema",
                json_schema={
                    "name": "moderation_response",
                    "strict": True,
                    "schema": dynamic_schema
                }
            )
            
            # DEBUG: Output the schema for debugging
            logger.info(
                "[SCHEMA DEBUG] Channel %s: %s",
                batch.channel_id,
                json.dumps(dynamic_schema, indent=2)
            )
            
            requests.append(ChannelBatchRequest(
                channel_id=batch.channel_id,
                guild_id=batch.guild_id,
                messages=messages,
                response_format=response_format,
                schema=dynamic_schema
            ))

        # Submit all requests concurrently and process results
        tasks = [
            self._make_request_and_parse(req)
            for req in requests
        ]
        
        results = await asyncio.gather(*tasks)
        
        # Group actions by channel
        actions_by_channel: Dict[int, List[ActionData]] = {
            channel_id.to_int(): actions
            for channel_id, actions in results
        }

        return actions_by_channel

    async def _make_request_and_parse(
        self, 
        req: ChannelBatchRequest
    ) -> tuple[ChannelID, List[ActionData]]:
        """Make API request and parse response into actions.
        
        Args:
            req: ChannelBatchRequest containing all data for this request.
            
        Returns:
            Tuple of (channel_id, list of actions).
        """
        try:
            response = await self._client.chat.completions.create(
                model=self._model_name,
                messages=req.messages,
                response_format=req.response_format,
            )
            response_text = response.choices[0].message.content or ""
            
        except Exception as exc:
            logger.error("[LLM ENGINE] API request failed for channel %s: %s", req.channel_id, exc)
            response_text = f"null: api error - {exc}"

        # Parse response into actions
        actions = moderation_parsing.parse_batch_actions(
            response_text,
            req.channel_id,
            req.guild_id,
            req.schema
        )

        # Log summary
        action_summary = ", ".join(f"{a.action}({a.user_id})" for a in actions if a.action != "null")
        logger.info(
            "[RESULT] Channel %s: %d actions [%s] | Response: \n%s",
            req.channel_id,
            len([a for a in actions if a.action != "null"]),
            action_summary or "none",
            response_text
        )

        return req.channel_id, actions