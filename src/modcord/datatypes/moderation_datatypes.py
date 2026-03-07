from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Tuple

import discord

from modcord.datatypes.discord_datatypes import ChannelID, UserID, DiscordUsername, GuildID, MessageID
from modcord.datatypes.image_datatypes import ImageID, ImageLink


@dataclass(frozen=True, slots=True)
class ModerationImage:
    image_id: ImageID
    image_url: ImageLink


@dataclass(frozen=True, slots=True)
class ModerationMessage:
    message_id: MessageID
    user_id: UserID
    content: str
    timestamp: datetime
    guild_id: GuildID
    channel_id: ChannelID
    images: Tuple[ModerationImage, ...] = ()
    is_history: bool = False


@dataclass(frozen=True, slots=True)
class ModerationUserChannel:
    """A single channel's messages belonging to one user."""
    channel_id: ChannelID
    channel_name: str
    messages: Tuple[ModerationMessage, ...]


@dataclass(frozen=True, slots=True)
class ModerationUser:
    user_id: UserID
    username: DiscordUsername
    join_date: datetime
    discord_member: discord.Member = field(hash=False, compare=False)
    discord_guild: discord.Guild = field(hash=False, compare=False)
    roles: Tuple[str, ...]
    channels: Tuple[ModerationUserChannel, ...]



@dataclass(frozen=True, slots=True)
class ChannelContext:
    """Metadata about a channel that contributed messages to a server batch."""
    channel_id: ChannelID
    channel_name: str
    guidelines: str = ""
    message_count: int = 0


@dataclass(frozen=True, slots=True)
class ServerModerationBatch:
    """A batch of messages across all channels in a guild for server-wide AI moderation."""
    guild_id: GuildID
    guild_name: str
    channels: Dict[ChannelID, ChannelContext] = field(default_factory=dict)
    users: Tuple[ModerationUser, ...] = ()
    history_users: Tuple[ModerationUser, ...] = ()


    def is_empty(self) -> bool:
        return not self.users or all(len(u.channels) == 0 for u in self.users)