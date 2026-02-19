"""High-level orchestration logic for AI-driven moderation workflows.

This module coordinates the entire moderation pipeline using an OpenAI-compatible API:
- Converting server-wide batches into chat completion requests with multimodal content.
- Dynamically building JSON schemas for structured outputs.
- Submitting a single request per guild per batch interval.
- Parsing responses and returning moderation actions.

Key Features:
- Uses AsyncOpenAI client for inference (compatible with vLLM, LM Studio, etc.).
- Supports multimodal inputs (text + images via URLs).
- Handles per-guild server rules dynamically (channel guidelines in payload).
- One API call per server per batch for token efficiency.
"""

from __future__ import annotations

import json
from typing import List

import weave
from openai import AsyncOpenAI
from openai.types.shared_params.response_format_json_schema import ResponseFormatJSONSchema

from modcord.ai import llm_payload_builder
from modcord.configuration.app_configuration import app_config
from modcord.datatypes.action_datatypes import ActionData
from modcord.datatypes.discord_datatypes import GuildID
from modcord.datatypes.moderation_datatypes import ServerModerationBatch
from modcord.moderation import moderation_parsing
from modcord.settings.guild_settings_manager import guild_settings_manager
from modcord.util.logger import get_logger

logger = get_logger("llm_engine")


class LLMEngine:
    """
    Coordinate moderation prompts, inference, and response parsing.

    This class manages the moderation pipeline using an OpenAI-compatible API:
    - Initializing the AsyncOpenAI client from configuration.
    - Converting a server-wide batch into a single chat completion request.
    - Dynamically generating JSON schemas for structured outputs.
    - Parsing responses into ActionData objects.
    """

    def __init__(self) -> None:
        """Initialize the LLMEngine with AsyncOpenAI client."""
        ai_settings = app_config.ai_settings
        weave.init("modcord")
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
        guild_rules = (await guild_settings_manager.get_rules(guild_id) or app_config.server_rules).strip()

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
        logger.info("[MODERATION] Processing server batch for guild %s", batch.guild_id)

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

        logger.debug(
            "[SCHEMA DEBUG] Guild %s: %s",
            batch.guild_id,
            json.dumps(dynamic_schema, indent=2),
        )

        # Make API request
        try:
            response = await self._client.chat.completions.create(
                model=self._model_name,
                messages=messages,
                response_format=response_format,
                reasoning_effort="low",
                #extra_body={'thinking': {'type': 'disabled'}, 'chat_template_kwargs': {"thinking": False}},
            )
            
            response_text = response.choices[0].message.content or "None, I don't know why. Report this as a bug to the developers!!!"

            logger.debug(
                "[LLM RESPONSE] Guild %s: \n\n%s",
                batch.guild_id,
                response_text,
            )

        except Exception as exc:
            logger.error("[LLM ENGINE] API request failed for guild %s: %s", batch.guild_id, exc)
            response_text = f"null: api error - {exc}"

        # Parse response into actions
        actions = moderation_parsing.parse_batch_actions(
            response_text,
            batch.guild_id,
            dynamic_schema,
        )

        return actions