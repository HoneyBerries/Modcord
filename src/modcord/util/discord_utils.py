"""
discord_utils.py
================

Low-level Discord utility functions for Modcord.

This module provides stateless helpers for Discord-specific operations, including message deletion, DM sending, permission checks, and moderation actions. All logic here is designed for use by higher-level bot components and should not maintain state.
"""


import asyncio
import datetime
from typing import Mapping, Union

import discord

from modcord.util.logger import get_logger
from modcord.moderation.moderation_datatypes import ActionData, ActionType, ModerationMessage
from modcord.database.database import log_moderation_action

logger = get_logger("discord_utils")

# ==========================================
# Duration/constants and choices (moved here so discord_utils is self-contained)
# ==========================================

# Human-friendly label for a permanent duration
PERMANENT_DURATION = "Till the end of time"

DURATIONS = {
    "60 secs": 1,
    "5 mins": 5,
    "10 mins": 10,
    "30 mins": 30,
    "1 hour": 60,
    "2 hours": 120,
    "1 day": 24 * 60,
    "1 week": 7 * 24 * 60,
    PERMANENT_DURATION: 0,
}

DURATION_CHOICES = list(DURATIONS.keys())

DELETE_MESSAGE_CHOICES = [
    discord.OptionChoice(name="Don't Delete Any", value=0),
    discord.OptionChoice(name="Previous Hour", value=60),
    discord.OptionChoice(name="Previous 6 Hours", value=6 * 60),
    discord.OptionChoice(name="Previous 12 Hours", value=12 * 60),
    discord.OptionChoice(name="Previous 24 Hours", value=24 * 60),
    discord.OptionChoice(name="Previous 3 Days", value=3 * 24 * 60),
    discord.OptionChoice(name="Previous 7 Days", value=7 * 24 * 60),
]


# ==========================================
# Helpers copied from bot_helper (Discord-specific, safe to live here)
# ==========================================

def bot_can_manage_messages(channel: discord.TextChannel, guild: discord.Guild) -> bool:
    """
    Determine if the bot has permission to read and manage messages in a given text channel.

    Args:
        channel (discord.TextChannel): The channel to check permissions for.
        guild (discord.Guild): The guild context to resolve the bot's member object.

    Returns:
        bool: True if the bot can read and manage messages, False otherwise.
    """
    me = getattr(guild, "me", None)
    if me is None:
        return True

    try:
        permissions = channel.permissions_for(me)
    except Exception:  # pragma: no cover - discord internals guard
        return False

    return permissions.read_messages and permissions.manage_messages


def iter_moderatable_channels(guild: discord.Guild):
    """
    Iterate over text channels in a guild where the bot can safely manage messages.

    Args:
        guild (discord.Guild): The guild whose channels are inspected.

    Yields:
        discord.TextChannel: Channels suitable for moderation actions.
    """
    for channel in getattr(guild, "text_channels", []):
        try:
            if bot_can_manage_messages(channel, guild):
                yield channel
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.debug(f"Skipping channel {getattr(channel, 'name', 'unknown')} due to error: {exc}")


# Note: TIMEOUT_ACTIONS was removed as it was only used in one place



def is_ignored_author(author: Union[discord.User, discord.Member]) -> bool:
    """
    Check if an author should be ignored by moderation handlers (e.g., bots or non-members).

    Args:
        author (discord.User | discord.Member): The user or member to check.

    Returns:
        bool: True if the author is a bot or not a member, False otherwise.
    """
    return author.bot or not isinstance(author, discord.Member)


def has_elevated_permissions(member: Union[discord.User, discord.Member]) -> bool:
    """
    Check if a member has moderator-level privileges (administrator, manage guild, or moderate members).

    Args:
        member (discord.User | discord.Member): The member to evaluate.

    Returns:
        bool: True if the member has elevated permissions, False otherwise.
    """

    if not isinstance(member, discord.Member):
        return False

    perms = member.guild_permissions
    return any(
        getattr(perms, attr, False)
        for attr in (
            "administrator",
            "manage_guild",
            "moderate_members",
        )
    )


# Note: build_dm_message removed - we now send embeds to DMs instead of text messages


def format_duration(seconds: int) -> str:
    """
    Convert a duration in seconds to a human-readable string.

    Args:
        seconds (int): Duration in seconds.

    Returns:
        str: Human-readable duration string.
    """
    if seconds == 0:
        return PERMANENT_DURATION
    elif seconds < 60:
        return f"{seconds} secs"
    elif seconds < 3600:
        mins = seconds // 60
        return f"{mins} mins"
    elif seconds < 86400:
        hours = seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''}"
    else:
        days = seconds // 86400
        return f"{days} day{'s' if days != 1 else ''}"


def parse_duration_to_minutes(human_readable_duration: str) -> int:
    """
    Convert a human-readable duration label to its value in minutes.

    Args:
        human_readable_duration (str): Duration label from DURATION_CHOICES.

    Returns:
        int: Duration in minutes, or 0 if not found.
    """
    return DURATIONS.get(human_readable_duration, 0)


async def create_punishment_embed(
    action_type: ActionType,
    user: discord.User | discord.Member,
    reason: str,
    duration_str: str | None = None,
    issuer: discord.User | discord.Member | discord.ClientUser | None = None,
    bot_user: discord.ClientUser | None = None
) -> discord.Embed:
    """
    Build a standardized embed summarizing a moderation action for logging or notification.

    Args:
        action_type (ActionType): The type of moderation action.
        user (discord.User | discord.Member): The affected user.
        reason (str): Reason for the action.
        duration_str (str | None): Optional duration label.
    issuer (discord.User | discord.Member | discord.ClientUser | None): Moderator responsible for the action.
    bot_user (discord.ClientUser | None): Bot user for footer labeling.

    Returns:
        discord.Embed: The constructed embed object.
    """
    details = {
        ActionType.BAN:     ("🔨", "Ban", discord.Color.red()),
        ActionType.KICK:    ("👢", "Kick", discord.Color.orange()),
        ActionType.WARN:    ("⚠️", "Warn", discord.Color.yellow()),
        ActionType.TIMEOUT: ("⏱️", "Timeout", discord.Color.blue()),
        ActionType.DELETE:  ("🗑️", "Delete", discord.Color.light_grey()),
        ActionType.UNBAN:   ("🔓", "Unban", discord.Color.green()),
        ActionType.NULL:    ("❓", "No Action", discord.Color.light_grey()),
    }.get(action_type, ("❓", "No Action", discord.Color.light_grey()))

    emoji, label, color = details

    embed = discord.Embed(
        title=f"{emoji} {label} Issued",
        color=color,
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    embed.add_field(name="User", value=f"{user.mention} (`{user.id}`)", inline=True)
    embed.add_field(name="Action", value=label, inline=True)
    if issuer:
        embed.add_field(name="Moderator", value=issuer.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)

    if duration_str:
        if duration_str != PERMANENT_DURATION:
            duration_minutes = parse_duration_to_minutes(duration_str)
            if duration_minutes > 0:
                expire_time = discord.utils.utcnow() + datetime.timedelta(minutes=duration_minutes)
                embed.add_field(
                    name="Duration",
                    value=f"{duration_str} (Expires: <t:{int(expire_time.timestamp())}:R>)",
                    inline=False,
                )
            else:
                embed.add_field(name="Duration", value=duration_str, inline=False)
        else:
            embed.add_field(name="Duration", value=duration_str, inline=False)

    embed.set_footer(text=f"Bot: {bot_user.name if bot_user else ''}")
    return embed


async def delete_recent_messages(guild, member, seconds) -> int:
    """
    Delete recent messages from a member across all moderatable channels within a time window.

    Args:
        guild (discord.Guild): The guild to search for messages.
        member (discord.Member): The member whose messages are deleted.
        seconds (int): Time window in seconds to look back.

    Returns:
        int: Number of messages deleted.
    """
    if seconds <= 0:
        return 0

    window_start = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=seconds)
    deleted_count = 0

    for channel in iter_moderatable_channels(guild):
        try:
            async for message in channel.history(after=window_start):
                if message.author.id == member.id and await safe_delete_message(message):
                    deleted_count += 1
        except Exception as exc:
            logger.error(f"Error deleting messages in {getattr(channel, 'name', '')}: {exc}")

    return deleted_count


async def delete_messages_background(ctx: discord.ApplicationContext, user: discord.Member, delete_message_minutes: int):
    """
    Delete a user's messages in the background and notify the command invoker of the result.

    Args:
        ctx (discord.ApplicationContext): The command context for follow-up messaging.
        user (discord.Member): The member whose messages are deleted.
        delete_message_minutes (int): Time window in minutes to look back.
    """
    try:
        seconds = delete_message_minutes * 60
        deleted = await delete_recent_messages(ctx.guild, user, seconds)
        if deleted:
            await ctx.followup.send(f"🗑️ Deleted {deleted} recent messages from {user.mention}.", ephemeral=True)
        else:
            await ctx.followup.send(f"No recent messages found to delete from {user.mention}.", ephemeral=True)
    except Exception as e:
        logger.error(f"Error deleting messages in background: {e}")
        await ctx.followup.send("⚠️ Action completed, but failed to delete some messages.", ephemeral=True)


# Shared sets for timeout-like actions
# Note: Format/DM/embed helpers and channel iteration originally lived in
# `bot_helper.py` and are intentionally returned there. This module keeps
# only Discord-specific low-level utilities and the shared duration constants.


from modcord.scheduler.unban_scheduler import (
    schedule_unban,
)

# --- Public Discord utility functions ---

async def safe_delete_message(message: discord.Message) -> bool:
    """
    Attempt to delete a Discord message, suppressing recoverable errors.

    Args:
        message (discord.Message): The message to delete.

    Returns:
        bool: True if deletion succeeded, False otherwise.
    """
    try:
        await message.delete()
        return True
    except discord.NotFound:
        return False
    except discord.Forbidden:
        logger.warning(f"No permission to delete message {message.id}")
    except Exception as exc:
        logger.error(f"Error deleting message {message.id}: {exc}")
    return False


async def delete_messages_by_ids(guild: discord.Guild, message_ids: list[str]) -> int:
    """
    Delete specific messages by their IDs across all moderatable channels in a guild.
    
    Uses concurrent operations for improved performance when deleting multiple messages.

    Args:
        guild (discord.Guild): The guild to search for messages.
        message_ids (list[str]): List of message IDs to delete.

    Returns:
        int: Number of messages deleted.
    """
    if not message_ids:
        return 0
    
    # Convert to integer IDs and filter invalid ones
    pending_ids = set()
    for raw_id in message_ids:
        try:
            pending_ids.add(int(raw_id))
        except Exception:
            logger.warning(f"Skipping invalid message id: {raw_id}")
    
    if not pending_ids:
        return 0
    
    deleted_count = 0
    channels = list(iter_moderatable_channels(guild))
    
    # Optimize by trying to fetch and delete messages concurrently from each channel
    for channel in channels:
        if not pending_ids:
            break
        
        # Create tasks for fetching messages concurrently
        fetch_tasks = []
        message_id_list = list(pending_ids)
        
        for message_id in message_id_list:
            fetch_tasks.append(asyncio.create_task(_fetch_and_delete_message(channel, message_id)))
        
        # Wait for all fetch/delete operations in this channel
        results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
        
        for message_id, result in zip(message_id_list, results):
            if isinstance(result, Exception):
                # Message not found or other error - remove from pending
                if not isinstance(result, discord.HTTPException):
                    logger.error(f"Error processing message {message_id} in {getattr(channel, 'name', '')}: {result}")
                pending_ids.discard(message_id)
            elif result:
                # Successfully deleted
                deleted_count += 1
                pending_ids.discard(message_id)
            # If result is False, message wasn't in this channel, keep in pending_ids
    
    if pending_ids:
        logger.debug(f"Failed to locate messages: {sorted(pending_ids)}")
    return deleted_count


async def _fetch_and_delete_message(channel: discord.TextChannel, message_id: int) -> bool:
    """
    Helper to fetch and delete a message from a channel.
    
    Args:
        channel (discord.TextChannel): The channel to fetch from.
        message_id (int): The message ID to fetch and delete.
    
    Returns:
        bool: True if deleted, False if not found in this channel.
    
    Raises:
        Exception: If an unexpected error occurs.
    """
    try:
        message = await channel.fetch_message(message_id)
        return await safe_delete_message(message)
    except discord.NotFound:
        return False
    except discord.Forbidden:
        return False


async def delete_recent_messages_by_count(guild: discord.Guild, member: discord.Member, count: int) -> int:
    """
    Delete the most recent messages from a member up to a specified count.

    Args:
        guild (discord.Guild): The guild to search for messages.
        member (discord.Member): The member whose messages are deleted.
        count (int): Maximum number of messages to delete.

    Returns:
        int: Number of messages deleted.
    """
    if count <= 0:
        return 0
    deleted = 0
    for channel in iter_moderatable_channels(guild):
        try:
            async for message in channel.history(limit=count - deleted):
                if message.author == member and await safe_delete_message(message):
                    deleted += 1
                if deleted >= count:
                    return deleted
        except Exception as exc:
            logger.error(f"Error in channel {getattr(channel, 'name', '')}: {exc}")
    return deleted


async def execute_moderation_notification(
    action_type: ActionType,
    user: discord.Member,
    guild: discord.Guild,
    reason: str,
    channel: discord.TextChannel | discord.Thread | None = None,
    duration_str: str | None = None,
    bot_user: discord.ClientUser | None = None,
) -> None:
    """
    Unified notification handler for moderation actions.
    
    Sends DM to user and posts embed to channel in one consolidated operation.
    All errors are suppressed to ensure notifications don't block actions.

    Args:
        action_type (ActionType): The moderation action type.
        user (discord.Member): The affected user.
        guild (discord.Guild): The guild where action occurred.
        reason (str): The reason for the action.
        channel (discord.TextChannel | discord.Thread | None): Channel to post embed to.
        duration_str (str | None): Optional duration label.
        bot_user (discord.ClientUser | None): Bot user for footer/issuer.
    """
    # Create the embed once for both DM and channel
    embed = await create_punishment_embed(
        action_type, user, reason, duration_str, issuer=None, bot_user=bot_user
    )
    
    if not embed:
        logger.error(f"Failed to create embed for {action_type.value}")
        return
    
    # Send DM with embed (suppressing errors)
    try:
        await user.send(embed=embed)
    except discord.Forbidden:
        logger.debug(f"Could not DM {user.display_name} for {action_type.value}: DMs disabled")
    except Exception as exc:
        logger.debug(f"Failed to DM user for {action_type.value}: {exc}")
    
    # Send embed to channel (suppressing errors)
    if channel and isinstance(channel, (discord.TextChannel, discord.Thread)):
        try:
            await channel.send(embed=embed)
        except Exception as exc:
            logger.error(f"Failed to send moderation embed to channel: {exc}")


# Note: Old send_dm_and_embed function removed - use execute_moderation_notification instead


def has_permissions(application_context: discord.ApplicationContext, **required_permissions) -> bool:
    """
    Check if the command issuer has all specified permissions in the guild.

    Args:
        application_context (discord.ApplicationContext): The command context.
        **required_permissions: Permission flags to check.

    Returns:
        bool: True if all permissions are present, False otherwise.
    """
    if not isinstance(application_context.author, discord.Member):
        return False
    return all(getattr(application_context.author.guild_permissions, permission_name, False) for permission_name in required_permissions)


# --- Main moderation action entry point ---

async def apply_action_decision(
    action: ActionData,
    pivot: ModerationMessage,
    bot_user: discord.ClientUser,
    bot_client: discord.Bot,
    *,
    message_lookup: Mapping[str, discord.Message] | None = None,
) -> bool:
    """
    Execute a moderation action decision produced by the AI pipeline, including message deletion, user moderation, notification, and logging.

    Args:
        action (ActionData): The moderation action to apply.
        pivot (ModerationMessage): The message that triggered moderation.
    bot_user (discord.ClientUser): The bot's user object.
        bot_client (discord.Bot): The bot client instance.
        message_lookup (Mapping[str, discord.Message] | None): Optional cache of messages for deletion.

    Returns:
        bool: True if the action was applied successfully, False otherwise.
    """

    if action.action is ActionType.NULL:
        logger.debug("Ignoring null moderation action for user %s", action.user_id)
        return True

    discord_message = pivot.discord_message
    if not discord_message or not discord_message.guild or not isinstance(discord_message.author, discord.Member):
        logger.warning("Invalid discord message or author for moderation pivot %s; skipping action", pivot.message_id)
        return False

    guild = discord_message.guild
    author = discord_message.author
    channel = discord_message.channel
    logger.debug("Executing %s on user %s (%s) for reason '%s'", action.action.value, author.display_name, author.id, action.reason)

    # Delete pivot message
    await safe_delete_message(discord_message)

    # Delete referenced messages except the pivot
    message_ids = [mid for mid in (action.message_ids or []) if mid and mid != str(discord_message.id)]
    if message_ids:
        cached_messages = message_lookup or {}
        delete_queue = [mid for mid in message_ids if cached_messages.get(mid) is None]
        deleted_total = 0
        for mid in message_ids:
            msg = cached_messages.get(mid)
            if msg:
                if await safe_delete_message(msg):
                    deleted_total += 1
        if delete_queue:
            try:
                deleted_total += await delete_messages_by_ids(guild, delete_queue)
            except Exception as exc:
                logger.error("Failed to delete referenced messages %s: %s", sorted(delete_queue), exc)
        logger.debug("Deleted %s referenced messages for user %s", deleted_total, author.display_name)

    if action.action is ActionType.DELETE:
        return True

    success = True

    # Execute the specified moderation action
    # Notifications (DM + channel embed) are handled by execute_moderation_notification

    match action.action:
        case ActionType.BAN:
            duration_minutes = int(action.ban_duration or 0)
            if duration_minutes == 0:
                logger.debug("Ban duration is 0 (not applicable); skipping ban for user %s", action.user_id)
                return True
            is_permanent = duration_minutes == -1
            if is_permanent:
                duration_seconds = 0
                duration_label = PERMANENT_DURATION
            else:
                duration_seconds = duration_minutes * 60
                duration_label = format_duration(duration_seconds)
            
            try:
                await guild.ban(author, reason=f"AI Mod: {action.reason}")
                await execute_moderation_notification(
                    action_type=ActionType.BAN,
                    user=author,
                    guild=guild,
                    reason=action.reason,
                    channel=channel,
                    duration_str=duration_label,
                    bot_user=bot_user
                )
            except Exception as exc:
                logger.error("Failed to ban user %s: %s", author.id, exc)
                return False
                
            if not is_permanent:
                try:
                    await schedule_unban(
                        guild=guild,
                        user_id=author.id,
                        channel=channel if isinstance(channel, (discord.TextChannel, discord.Thread)) else None,
                        duration_seconds=duration_seconds,
                        bot=bot_client,
                        reason="Ban duration expired.",
                    )
                except Exception as exc:
                    logger.error("Failed to schedule unban for user %s: %s", author.id, exc)
                    success = False


        case ActionType.KICK:
            try:
                await guild.kick(author, reason=f"AI Mod: {action.reason}")
                await execute_moderation_notification(
                    action_type=ActionType.KICK,
                    user=author,
                    guild=guild,
                    reason=action.reason,
                    channel=channel,
                    duration_str=None,
                    bot_user=bot_user
                )
            except Exception as exc:
                logger.error("Failed to kick user %s: %s", author.id, exc)
                return False
            

        case ActionType.TIMEOUT:
            duration_minutes = action.timeout_duration if action.timeout_duration is not None else 0
            if duration_minutes == 0:
                logger.debug("Timeout duration is 0 (not applicable); skipping timeout for user %s", action.user_id)
                return True
            if duration_minutes == -1:
                duration_minutes = 28 * 24 * 60  # 28 days in minutes
            duration_seconds = duration_minutes * 60
            duration_label = format_duration(duration_seconds)
            until = discord.utils.utcnow() + datetime.timedelta(seconds=duration_seconds)
            
            try:
                await author.timeout(until, reason=f"AI Mod: {action.reason}")
                await execute_moderation_notification(
                    action_type=ActionType.TIMEOUT,
                    user=author,
                    guild=guild,
                    reason=action.reason,
                    channel=channel,
                    duration_str=duration_label,
                    bot_user=bot_user
                )
            except Exception as exc:
                logger.error("Failed to timeout user %s: %s", author.id, exc)
                return False
            

        case ActionType.WARN:
            try:
                await execute_moderation_notification(
                    action_type=ActionType.WARN,
                    user=author,
                    guild=guild,
                    reason=action.reason,
                    channel=channel,
                    duration_str=None,
                    bot_user=bot_user
                )
            except Exception as exc:
                logger.error("Failed to process warn for user %s: %s", author.id, exc)
                return False
            

        case ActionType.UNBAN:
            try:
                await execute_moderation_notification(
                    action_type=ActionType.UNBAN,
                    user=author,
                    guild=guild,
                    reason=action.reason,
                    channel=channel,
                    duration_str=None,
                    bot_user=bot_user
                )
            except Exception as exc:
                logger.error("Failed to create unban embed for user %s: %s", author.id, exc)
                return False
        case _:
            pass

    # Log the action to the database if successful
    if success and action.action != ActionType.NULL:
        try:
            metadata = {}
            match action.action:
                case ActionType.BAN:
                    metadata["ban_duration"] = action.ban_duration
                case ActionType.TIMEOUT:
                    metadata["timeout_duration"] = action.timeout_duration
                case ActionType.DELETE:
                    metadata["message_ids"] = action.message_ids
                case ActionType.KICK:
                    pass  # No extra metadata for kick
                case ActionType.WARN:
                    pass  # No extra metadata for warn
                case _:
                    pass

            if action.message_ids and action.action != ActionType.DELETE:
                metadata["message_ids"] = action.message_ids

            await log_moderation_action(
                guild_id=guild.id,
                user_id=action.user_id,
                action_type=action.action.value,
                reason=action.reason,
                metadata=metadata if metadata else None
            )

        except Exception as exc:
            logger.error("Failed to log moderation action to database: %s", exc)

    return success