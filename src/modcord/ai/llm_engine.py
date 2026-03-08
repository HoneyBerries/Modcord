"""High-level orchestration logic for AI-driven moderation workflows.

This module coordinates the entire moderation pipeline using an OpenAI-compatible API:
- Converting server-wide batches into chat completion requests with multimodal content.
- Dynamically building JSON schemas for structured outputs.
- Submitting a single request per guild per batch interval.
- Parsing responses and returning moderation actions.

Key Features:
- Uses AsyncOpenAI client for inference (compatible with vLLM, LM Studio, etc.).
- Supports multimodal inputs (text and images via URLs).
- Handles per-guild server rules dynamically (channel guidelines in payload).
- One API call per server per batch for token efficiency.
"""

from __future__ import annotations

from typing import List

import weave

weave.init("modcord")

from openai import AsyncOpenAI
from openai.types.shared_params.response_format_json_schema import ResponseFormatJSONSchema

from modcord.ai import llm_payload_builder
from modcord.configuration.app_configuration import app_config
from modcord.datatypes.action_datatypes import ActionData
from modcord.datatypes.discord_datatypes import GuildID
from modcord.datatypes.moderation_datatypes import ServerModerationBatch
from modcord.moderation import llm_json_parser
from modcord.settings.guild_settings_manager import guild_settings_manager
from modcord.util.logger import get_logger

logger = get_logger("LLM ENGINE")


class LLMEngine:
    """
    Coordinate moderation prompts, inference, and response parsing.

    This class manages the moderation pipeline using an OpenAI-compatible API:
    - Initializing the AsyncOpenAI client from configuration.
    - Converting a server-wide batch into a single chat completion request.
    - Dynamically generating JSON schemas for structured outputs.
    - Parsing responses into ActionData objects.
    """

    def __init__(self, api_key: str, base_url: str) -> None:
        """Initialize the LLMEngine with an AsyncOpenAI client.

        Args:
            api_key: The OpenAI-compatible API key.
            base_url: The OpenAI-compatible API base URL.
        """
        ai_settings = app_config.ai_settings
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        self._model_name = ai_settings.model_name
        self._api_request_timeout = ai_settings.api_request_timeout
        self._base_system_prompt = app_config.system_prompt_template
        logger.info(
            "Initialized with base_url=%s, model=%s, api_request_timeout=%.1fs",
            ai_settings.base_url,
            self._model_name,
            self._api_request_timeout,
        )

    async def generate_dynamic_system_prompt(self, guild_id: GuildID) -> str:
        """Build the system prompt with guild-specific server rules.

        Channel-specific guidelines are now embedded per-channel in the
        JSON payload rather than injected into the system prompt.

        Args:
            guild_id: The guild ID to fetch rules from.

        Returns:
            Formatted system prompt string with injected server rules.
        """
        template = self._base_system_prompt

        # Resolve guild rules
        guild_rules = await guild_settings_manager.get_rules(guild_id) or app_config.generic_server_rules

        # Inject server rules; channel guidelines are in the payload
        prompt = template.replace("<|SERVER_RULES_INJECT|>", guild_rules)

        return prompt

    async def get_moderation_actions(
            self,
            batch: ServerModerationBatch,
    ) -> List[ActionData]:
        """
        Get moderation actions from AI for a server-wide batch.

        This method handles AI inference for a single guild batch:
        1. Builds system prompt with guild rules
        2. Converts batch to API request with dynamic schema
        3. Submits request to OpenAI-compatible API
        4. Parses response into ActionData objects

        Args:
            batch: ServerModerationBatch containing all users/messages across channels.

        Returns:
            List of ActionData objects parsed from the AI response.
        """
        logger.info("Processing server batch for guild %s", batch.guild_id)

        # Build system prompt with guild rules (no channel guidelines)
        system_prompt = await self.generate_dynamic_system_prompt(batch.guild_id)

        # Convert batch to OpenAI messages with dynamic schema
        messages, dynamic_schema = llm_payload_builder.convert_batch_to_openai_messages(batch, system_prompt)

        # Convert dynamic output schema to OpenAI-compatible format
        response_format = ResponseFormatJSONSchema(
            type="json_schema",
            json_schema={
                "name": "moderation_response",
                "strict": True,
                "schema": dynamic_schema,
            },
        )

        # Make API request
        response = await self.create_completion(messages, response_format, self._model_name, "low",
                                                self._api_request_timeout)
        response_text = (response.choices[0].message.content
                         or "None, I don't know why. Report this as a bug to the developers!!!")

        logger.debug(
            "Guild %s: \n\n%s",
            batch.guild_id,
            response_text,
        )

        # Parse response into actions
        actions = llm_json_parser.parse_batch_actions(
            response_text,
            batch.guild_id,
            dynamic_schema,
        )

        return actions


    @weave.op(name="LLM Inference", call_display_name="Modcord Inference LLM Request", enable_code_capture=True,
              eager_call_start=True)
    async def create_completion(self, message, response_format, model, reasoning_effort, timeout, extra_body=None):
        try:
            return await self._client.chat.completions.create(
                model=model,
                messages=message,
                response_format=response_format,
                reasoning_effort=reasoning_effort,
                temperature=0.7,
                seed=0,
                timeout=timeout,
                extra_body=extra_body,
            )

        except Exception as e:
            logger.error("Error during LLM inference: %s", e)
