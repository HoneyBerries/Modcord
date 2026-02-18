"""
Build AI-ready payloads from server moderation batches.

- Merges current and historical messages
- Deduplicates messages by ID
- Adds timestamps, roles, and images
- Generates ChatCompletionMessageParam list ready for OpenAI API
"""

from __future__ import annotations
from typing import Dict, List, Tuple
from collections import defaultdict
import json

from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
    ChatCompletionContentPartTextParam,
    ChatCompletionContentPartImageParam,
)

from modcord.datatypes.discord_datatypes import UserID
from modcord.datatypes.moderation_datatypes import (
    ServerModerationBatch,
    ModerationUser,
    ModerationMessage,
)
from modcord.util.format_utils import humanize_timestamp
from modcord.util.logger import get_logger
from . import dynamic_schema_generator

logger = get_logger("llm_payload_builder")

def merge_users_with_history(
    current_users: Tuple[ModerationUser, ...],
    history_users: Tuple[ModerationUser, ...],
) -> Tuple[Dict[UserID, ModerationUser], Dict[UserID, Tuple[ModerationMessage, ...]]]:
    """
    Merge current and historical users/messages, deduplicating by message_id.
    """
    user_map: Dict[UserID, ModerationUser] = {}
    
    # Use list as the factory for efficiency during collection
    messages_by_user_list: Dict[UserID, list] = defaultdict(list)
    seen_message_ids = set()

    # Combine both iterables
    for user in current_users + history_users:
        # Keep the first instance of the user object encountered
        user_map.setdefault(user.user_id, user)
        
        for msg in user.messages:
            if msg.message_id not in seen_message_ids:
                messages_by_user_list[user.user_id].append(msg)
                seen_message_ids.add(msg.message_id)

    # Convert lists back to tuples to match the return type signature
    messages_by_user = {
        user_id: tuple(msgs) 
        for user_id, msgs in messages_by_user_list.items()
    }

    return user_map, messages_by_user


def convert_batch_to_openai_messages(
    batch: ServerModerationBatch,
    system_prompt: str,
) -> Tuple[List[ChatCompletionMessageParam], dict]:
    """
    Convert a ServerModerationBatch to OpenAI ChatCompletionMessageParam list.

    - Includes history
    - Deduplicates by message_id
    - Adds timestamps and roles
    - Inline images labeled as Image <id>
    """
    user_map, messages_by_user = merge_users_with_history(
        batch.users,
        batch.history_users
    )

    all_images: List[Tuple[str, str]] = []

    users_data = []
    total_messages = 0

    for user_id, user in user_map.items():
        user_messages_data = []
        for msg in messages_by_user[user_id]:
            image_ids = []
            for img in msg.images:
                if img.image_id and img.image_url:
                    image_ids.append(str(img.image_id))
                    all_images.append(
                        (str(img.image_id), str(img.image_url))
                    )
            user_messages_data.append({
                "message_id": str(msg.message_id),
                "timestamp": humanize_timestamp(msg.timestamp),
                "content": msg.content or ("[Images only]" if image_ids else ""),
                "image_ids": image_ids
            })
            total_messages += 1

        users_data.append({
            "user_id": str(user.user_id),
            "username": str(user.username),
            "roles": user.roles,
            "messages": user_messages_data
        })

    json_payload = {
        "guild_id": str(batch.guild_id),
        "message_count": total_messages,
        "unique_user_count": len(user_map),
        "users": users_data,
    }

    content_parts: List[ChatCompletionContentPartTextParam | ChatCompletionContentPartImageParam] = [
        ChatCompletionContentPartTextParam(
            type="text",
            text=json.dumps(json_payload, separators=(",", ":"))
        )
    ]

    for image_id, image_url in all_images:
        content_parts.append(
            ChatCompletionContentPartTextParam(type="text", text=f"Image {image_id} (see below):")
        )
        content_parts.append(
            ChatCompletionContentPartImageParam(type="image_url", image_url={"url": image_url})
        )

    messages: List[ChatCompletionMessageParam] = [
        ChatCompletionSystemMessageParam(role="system", content=system_prompt),
        ChatCompletionUserMessageParam(role="user", content=content_parts)
    ]

    dynamic_schema = dynamic_schema_generator.build_server_moderation_schema(batch)

    logger.debug(
        "[PAYLOAD] Guild %s: users=%d messages=%d images=%d",
        batch.guild_id, len(user_map), total_messages, len(all_images)
    )

    return messages, dynamic_schema