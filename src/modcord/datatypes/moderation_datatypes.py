from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Tuple, Optional
import discord

from modcord.datatypes.discord_datatypes import ChannelID, UserID, DiscordUsername, GuildID, MessageID
from modcord.datatypes.image_datatypes import ImageID, ImageURL
from modcord.datatypes.action_datatypes import ActionData


@dataclass(frozen=True, slots=True)
class ModerationImage:
    image_id: ImageID
    image_url: ImageURL


@dataclass(frozen=True, slots=True)
class ModerationMessage:
    message_id: MessageID
    user_id: UserID
    content: str
    timestamp: datetime
    guild_id: GuildID
    channel_id: ChannelID
    images: Tuple[ModerationImage, ...] = ()


@dataclass(frozen=True, slots=True)
class ModerationUser:
    user_id: UserID
    username: DiscordUsername
    join_date: datetime
    discord_member: discord.Member = field(hash=False, compare=False)  # Keep discord.Member for actions
    discord_guild: discord.Guild = field(hash=False, compare=False)  # Keep discord.Guild for actions
    roles: Tuple[str, ...] = ()
    messages: Tuple[ModerationMessage, ...] = ()
    past_actions: Tuple[ActionData, ...] = ()

    def add_message(self, message: ModerationMessage) -> ModerationUser:
        return ModerationUser(
            user_id=self.user_id,
            username=self.username,
            join_date=self.join_date,
            discord_member=self.discord_member,
            discord_guild=self.discord_guild,
            roles=self.roles,
            messages=self.messages + (message,),
            past_actions=self.past_actions,
        )

    def add_past_action(self, action: ActionData) -> ModerationUser:
        return ModerationUser(
            user_id=self.user_id,
            username=self.username,
            join_date=self.join_date,
            discord_member=self.discord_member,
            discord_guild=self.discord_guild,
            roles=self.roles,
            messages=self.messages,
            past_actions=self.past_actions + (action,),
        )


@dataclass(frozen=True, slots=True)
class ModerationChannelBatch:
    guild_id: GuildID
    channel_id: ChannelID
    channel_name: str
    users: Tuple[ModerationUser, ...] = ()
    history_users: Tuple[ModerationUser, ...] = ()

    def add_user(self, user: ModerationUser) -> ModerationChannelBatch:
        return ModerationChannelBatch(
            guild_id=self.guild_id,
            channel_id=self.channel_id,
            channel_name=self.channel_name,
            users=self.users + (user,),
            history_users=self.history_users,
        )

    def extend_users(self, new_users: Tuple[ModerationUser, ...]) -> ModerationChannelBatch:
        return ModerationChannelBatch(
            guild_id=self.guild_id,
            channel_id=self.channel_id,
            channel_name=self.channel_name,
            users=self.users + new_users,
            history_users=self.history_users,
        )

    def set_history(self, new_history: Tuple[ModerationUser, ...]) -> ModerationChannelBatch:
        return ModerationChannelBatch(
            guild_id=self.guild_id,
            channel_id=self.channel_id,
            channel_name=self.channel_name,
            users=self.users,
            history_users=new_history,
        )

    def is_empty(self) -> bool:
        return not self.users or all(len(u.messages) == 0 for u in self.users)