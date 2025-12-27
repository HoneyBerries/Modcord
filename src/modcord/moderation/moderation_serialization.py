"""
Serialization utilities for converting moderation batches to AI-compatible payloads.

This module handles the transformation of moderation data structures into formats
suitable for AI inference, with a focus on building OpenAI-compatible messages directly.

Key Features:
- Direct conversion to OpenAI ChatCompletionMessageParam format
- Inline image handling (no separate ID mapping needed)
- User/message deduplication for historical context
- Clean, testable functions with single responsibilities
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Dict, List, Tuple

from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionContentPartParam,
    ChatCompletionContentPartImageParam,
    ChatCompletionContentPartTextParam,
)

from modcord.datatypes.discord_datatypes import UserID, MessageID
from modcord.datatypes.moderation_datatypes import (
    ModerationChannelBatch,
    ModerationUser,
    ModerationMessage,
)
from modcord.util.format_utils import humanize_timestamp, format_past_actions
from modcord.util.logger import get_logger
from modcord.ai import dynamic_schema_generator

logger = get_logger("moderation_serialization")


def merge_users_with_history(
    current_users: List[ModerationUser],
    history_users: List[ModerationUser],
) -> Tuple[Dict[UserID, ModerationUser], Dict[UserID, List[Tuple[ModerationMessage, bool]]]]:
    """Merge current and historical users, deduplicating messages.
    
    Combines users from the current batch with historical context, ensuring each 
    user appears once and messages are not duplicated. Historical messages are 
    marked with is_history=True.
    
    Args:
        current_users: Users from the current moderation batch.
        history_users: Users providing historical context.
    
    Returns:
        Tuple of:
        - user_map: Dict mapping UserID to ModerationUser (deduplicated)
        - messages_by_user: Dict mapping UserID to list of (message, is_history) tuples
    """
    user_map: Dict[UserID, ModerationUser] = {}
    messages_by_user: Dict[UserID, List[Tuple[ModerationMessage, bool]]] = defaultdict(list)
    
    # Collect current message IDs for deduplication
    current_message_ids = {msg.message_id for user in current_users for msg in user.messages}
    
    # Add current users and messages (is_history=False)
    for user in current_users:
        user_map.setdefault(user.user_id, user)
        messages_by_user[user.user_id].extend((msg, False) for msg in user.messages)
    
    # Add history users and non-duplicate messages (is_history=True)
    for user in history_users:
        user_map.setdefault(user.user_id, user)
        messages_by_user[user.user_id].extend(
            (msg, True) for msg in user.messages if msg.message_id not in current_message_ids
        )
    
    return user_map, messages_by_user


def convert_batch_to_openai_messages(
    batch: ModerationChannelBatch,
    system_prompt: str,
) -> Tuple[List[ChatCompletionMessageParam], Dict[str, Any]]:
    """Convert a moderation batch to OpenAI messages with dynamic schema.
    
    This is the primary entry point for preparing batches for AI inference.
    It builds the complete message list with inline images AND generates the
    dynamic JSON schema for structured outputs, all in one pass.
    
    The output format:
    - System message with the prompt
    - User message containing:
      - JSON text with batch metadata and user/message data
      - Inline images immediately after the JSON (with labels)
    - Dynamic schema constraining outputs to valid user/message IDs
    
    Args:
        batch: ModerationChannelBatch containing users, messages, and context.
        system_prompt: The system prompt to use for this inference.
    
    Returns:
        Tuple of:
        - messages: List of ChatCompletionMessageParam ready for API call
        - dynamic_schema: JSON schema dict constraining AI outputs
    """
    # Merge current and history users
    user_map, messages_by_user = merge_users_with_history(
        current_users=batch.users,
        history_users=batch.history_users,
    )
    
    # Build user->message_ids map for schema (non-history messages only)
    user_message_map: Dict[UserID, List[MessageID]] = {
        user.user_id: [msg.message_id for msg in user.messages]
        for user in batch.users
    }
    
    # Build JSON payload with user/message data
    users_data: List[Dict[str, Any]] = []
    all_images: List[Tuple[str, str]] = []  # (image_id, url) pairs
    total_messages = 0
    
    for user_id in sorted(user_map.keys(), key=lambda uid: uid.to_int()):
        user = user_map[user_id]
        messages_data: List[Dict[str, Any]] = []
        
        for msg, is_history in messages_by_user[user_id]:
            # Collect image IDs for this message
            msg_image_ids: List[str] = []
            for img in msg.images:
                if img.image_url and img.image_id:
                    img_id_str = str(img.image_id)
                    msg_image_ids.append(img_id_str)
                    all_images.append((img_id_str, img.image_url.to_string()))
            
            messages_data.append({
                "message_id": msg.message_id.to_int(),
                "timestamp": humanize_timestamp(msg.timestamp),
                "content": msg.content or ("[Images only]" if msg_image_ids else ""),
                "image_ids": msg_image_ids,
                "is_history": is_history,
            })
            total_messages += 1
        
        users_data.append({
            "user_id": user.user_id.to_int(),
            "username": str(user.username),
            "roles": user.roles,
            "join_date": humanize_timestamp(user.join_date),
            "message_count": len(messages_data),
            "messages": messages_data,
            "past_actions": format_past_actions(user.past_actions),
        })
    
    # Build the JSON payload
    json_payload = {
        "channel_id": batch.channel_id.to_int(),
        "channel_name": batch.channel_name,
        "message_count": total_messages,
        "unique_user_count": len(user_map),
        "total_images": len(all_images),
        "users": users_data,
    }
    
    # Build user message content parts
    user_content: List[ChatCompletionContentPartParam] = [
        ChatCompletionContentPartTextParam(
            type="text",
            text=json.dumps(json_payload, separators=(",", ":"))
        )
    ]
    
    # Add images inline with labels (deduplicated by image_id)
    seen_image_ids: set = set()
    for image_id, image_url in all_images:
        if image_id not in seen_image_ids:
            seen_image_ids.add(image_id)
            user_content.append(
                ChatCompletionContentPartTextParam(
                    type="text",
                    text=f"Image (ID: {image_id}):"
                )
            )
            user_content.append(
                ChatCompletionContentPartImageParam(
                    type="image_url",
                    image_url={"url": image_url}
                )
            )
    
    messages: List[ChatCompletionMessageParam] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    
    # Generate dynamic schema with user/message constraints
    dynamic_schema = dynamic_schema_generator.build_dynamic_moderation_schema(
        user_message_map, batch.channel_id
    )
    
    logger.debug(
        "[SERIALIZATION] Built OpenAI messages: %d users, %d messages, %d images",
        len(user_map),
        total_messages,
        len(seen_image_ids),
    )
    
    return messages, dynamic_schema