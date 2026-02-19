"""
Build AI-ready payloads from server moderation batches.

- Merges current and historical user-channel-message trees
- Deduplicates messages by ID within each channel
- Adds timestamps, roles, and images
- Generates ChatCompletionMessageParam list ready for OpenAI API
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Dict, List, Tuple

from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
    ChatCompletionContentPartTextParam,
    ChatCompletionContentPartImageParam,
)

from modcord.datatypes.discord_datatypes import ChannelID, UserID
from modcord.datatypes.moderation_datatypes import (
    ServerModerationBatch,
    ModerationUser,
    ModerationUserChannel,
    ModerationMessage,
)
from modcord.util.format_utils import humanize_timestamp
from modcord.util.logger import get_logger
from . import dynamic_schema_generator

logger = get_logger("llm_payload_builder")


def merge_users_with_history(
    current_users: Tuple[ModerationUser, ...],
    history_users: Tuple[ModerationUser, ...],
) -> Tuple[Dict[UserID, ModerationUser], Dict[UserID, Tuple[ModerationUserChannel, ...]]]:
    """
    Merge current and historical users, deduplicating messages per channel.

    Returns
    -------
    user_map : Dict[UserID, ModerationUser]
        First-seen ModerationUser object per user.
    channels_by_user : Dict[UserID, Tuple[ModerationUserChannel, ...]]
        Per-user channel groupings with deduplicated messages.
    """
    user_map: Dict[UserID, ModerationUser] = {}

    # user_id → channel_id → ordered list of messages (deduped)
    user_channel_msgs: Dict[UserID, Dict[ChannelID, List[ModerationMessage]]] = defaultdict(
        lambda: defaultdict(list)
    )
    # user_id → channel_id → channel_name (first seen wins)
    channel_names: Dict[UserID, Dict[ChannelID, str]] = defaultdict(dict)
    seen_message_ids: set = set()

    for user in current_users + history_users:
        user_map.setdefault(user.user_id, user)

        for uch in user.channels:
            channel_names[user.user_id].setdefault(uch.channel_id, uch.channel_name)
            for msg in uch.messages:
                if msg.message_id not in seen_message_ids:
                    user_channel_msgs[user.user_id][uch.channel_id].append(msg)
                    seen_message_ids.add(msg.message_id)

    # Convert to frozen ModerationUserChannel tuples
    channels_by_user: Dict[UserID, Tuple[ModerationUserChannel, ...]] = {}
    for uid, ch_map in user_channel_msgs.items():
        uchs: List[ModerationUserChannel] = []
        for ch_id, msgs in ch_map.items():
            uchs.append(
                ModerationUserChannel(
                    channel_id=ch_id,
                    channel_name=channel_names[uid].get(ch_id, f"Channel {ch_id}"),
                    messages=tuple(msgs),
                )
            )
        channels_by_user[uid] = tuple(uchs)

    return user_map, channels_by_user


def convert_batch_to_openai_messages(
    batch: ServerModerationBatch,
    system_prompt: str,
) -> Tuple[List[ChatCompletionMessageParam], dict]:
    """
    Convert a ServerModerationBatch to OpenAI ChatCompletionMessageParam list.

    JSON payload shape sent to AI:
        guild_id, message_count, unique_user_count,
        users[].user_id / username / roles /
            channels[].channel_id / channel_name /
                messages[].message_id / timestamp / content / image_ids
    """
    user_map, channels_by_user = merge_users_with_history(
        batch.users,
        batch.history_users,
    )

    all_images: List[Tuple[str, str]] = []
    users_data: List[dict] = []
    total_messages = 0

    for user_id, user in user_map.items():
        user_channels_data: List[dict] = []

        for uch in channels_by_user.get(user_id, ()):
            channel_messages_data: List[dict] = []

            for msg in uch.messages:
                image_ids: List[str] = []
                for img in msg.images:
                    if img.image_id and img.image_url:
                        image_ids.append(str(img.image_id))
                        all_images.append((str(img.image_id), str(img.image_url)))

                channel_messages_data.append({
                    "message_id": str(msg.message_id),
                    "timestamp": humanize_timestamp(msg.timestamp),
                    "content": msg.content or ("[Images only]" if image_ids else ""),
                    "image_ids": image_ids,
                })
                total_messages += 1

            user_channels_data.append({
                "channel_id": str(uch.channel_id),
                "channel_name": uch.channel_name,
                "messages": channel_messages_data,
            })

        users_data.append({
            "user_id": str(user.user_id),
            "username": str(user.username),
            "roles": user.roles,
            "channels": user_channels_data,
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
            text=json.dumps(json_payload, separators=(",", ":")),
        )
    ]

    for image_id, image_url in all_images:
        content_parts.append(
            ChatCompletionContentPartTextParam(type="text", text=f"Image {image_id} (see below/next/after this message):\n")
        )
        content_parts.append(
            ChatCompletionContentPartImageParam(type="image_url", image_url={"url": image_url})
        )

    messages: List[ChatCompletionMessageParam] = [
        ChatCompletionSystemMessageParam(role="system", content=system_prompt),
        ChatCompletionUserMessageParam(role="user", content=content_parts),
    ]

    dynamic_schema = dynamic_schema_generator.build_server_moderation_schema(batch)

    logger.debug(
        "[PAYLOAD] Guild %s: users=%d messages=%d images=%d",
        batch.guild_id, len(user_map), total_messages, len(all_images),
    )

    return messages, dynamic_schema