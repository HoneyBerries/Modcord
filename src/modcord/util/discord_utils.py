"""
discord_utils.py
================

Low-level Discord utility functions for Modcord.

This module provides stateless helpers for Discord-specific operations, including message deletion, DM sending, permission checks, and moderation actions. All logic here is designed for use by higher-level bot components and should not maintain state.
"""


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


# Shared sets for timeout-like actions
TIMEOUT_ACTIONS: set[ActionType] = {ActionType.TIMEOUT}



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


def build_dm_message(
    action: ActionType,
    guild_name: str,
    reason: str,
    duration_str: str | None = None,
) -> str:
    """
    Construct a DM message for a user based on the moderation action taken.

    Args:
        action (ActionType): The moderation action performed.
        guild_name (str): The name of the guild where the action occurred.
        reason (str): The reason for the action.
        duration_str (str | None): Optional duration for temporary actions.

    Returns:
        str: The DM message content.
    """
    if action == ActionType.BAN:
        if duration_str and duration_str != PERMANENT_DURATION:
            duration_fragment = f"for {duration_str}"
        else:
            duration_fragment = "permanently"
        return f"You have been banned from {guild_name} {duration_fragment}.\n**Reason**: {reason}"

    if action == ActionType.KICK:
        return f"You have been kicked from {guild_name}.\n**Reason**: {reason}"

    if action in TIMEOUT_ACTIONS:
        duration_label = duration_str or PERMANENT_DURATION
        return f"You have been timed out in {guild_name} for {duration_label}.\n**Reason**: {reason}"

    if action == ActionType.WARN:
        return f"You have received a warning in {guild_name}.\n**Reason**: {reason}"

    return ""


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
    issuer: discord.User | discord.Member | discord.BotUser | None = None,
    bot_user: discord.BotUser | None = None
) -> discord.Embed:
    """
    Build a standardized embed summarizing a moderation action for logging or notification.

    Args:
        action_type (ActionType): The type of moderation action.
        user (discord.User | discord.Member): The affected user.
        reason (str): Reason for the action.
        duration_str (str | None): Optional duration label.
        issuer (discord.User | discord.Member | discord.BotUser | None): Moderator responsible for the action.
        bot_user (discord.BotUser | None): Bot user for footer labeling.

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

    Args:
        guild (discord.Guild): The guild to search for messages.
        message_ids (list[str]): List of message IDs to delete.

    Returns:
        int: Number of messages deleted.
    """
    if not message_ids:
        return 0
    deleted_count = 0
    pending_ids = set()
    for raw_id in message_ids:
        try:
            pending_ids.add(int(raw_id))
        except Exception:
            logger.warning(f"Skipping invalid message id: {raw_id}")
    for channel in iter_moderatable_channels(guild):
        if not pending_ids:
            break
        for message_id in list(pending_ids):
            try:
                message = await channel.fetch_message(message_id)
                if await safe_delete_message(message):
                    deleted_count += 1
                pending_ids.discard(message_id)
            except (discord.NotFound, discord.Forbidden):
                pending_ids.discard(message_id)
            except Exception as exc:
                logger.error(f"Error fetching/deleting message {message_id} in {getattr(channel, 'name', '')}: {exc}")
                pending_ids.discard(message_id)
    if pending_ids:
        logger.debug(f"Failed to locate messages: {sorted(pending_ids)}")
    return deleted_count


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


async def send_dm_to_user(target_user: discord.Member, message_content: str) -> bool:
    """
    Attempt to send a direct message to a user, handling common errors.

    Args:
        target_user (discord.Member): The member to DM.
        message_content (str): The message content.

    Returns:
        bool: True if the DM was sent successfully, False otherwise.
    """
    try:
        await target_user.send(message_content)
        return True
    except discord.Forbidden:
        logger.warning(f"Could not DM {target_user.display_name}: They may have DMs disabled.")
    except Exception as e:
        logger.error(f"Failed to send DM to {target_user.display_name}: {e}")
    return False


async def send_dm_and_embed(
    ctx: discord.ApplicationContext,
    user: discord.Member,
    action_type: ActionType,
    reason: str,
    duration_str: str | None = None
):
    """
    Send a DM and a moderation embed to notify both the affected user and moderators about an action.

    Args:
        ctx (discord.ApplicationContext): The command context for follow-up messaging.
        user (discord.Member): The member receiving the DM.
        action_type (ActionType): The moderation action type.
        reason (str): The reason for the action.
        duration_str (str | None): Optional duration label.
    """
    dm_message = build_dm_message(action_type, ctx.guild.name, reason, duration_str)
    if not dm_message:
        dm_message = f"You have been {action_type.value}ed in {ctx.guild.name}.\n**Reason**: {reason}"
    await send_dm_to_user(user, dm_message)
    embed = await create_punishment_embed(action_type, user, reason, duration_str, bot_user=ctx.bot.user)
    await ctx.followup.send(embed=embed)


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
    bot_user: discord.BotUser,
    bot_client: discord.Bot,
    *,
    message_lookup: Mapping[str, discord.Message] | None = None,
) -> bool:
    """
    Execute a moderation action decision produced by the AI pipeline, including message deletion, user moderation, notification, and logging.

    Args:
        action (ActionData): The moderation action to apply.
        pivot (ModerationMessage): The message that triggered moderation.
        bot_user (discord.BotUser): The bot's user object.
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

    embed = None
    success = True

    # Execute the specified moderation action
    # Note: DM sending and embed creation are handled within each case

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
                await send_dm_to_user(author, build_dm_message(ActionType.BAN, guild.name, action.reason, duration_label))
            except Exception:
                logger.debug("Failed to DM user prior to ban, continuing with ban.")
            try:
                await guild.ban(author, reason=f"AI Mod: {action.reason}")
                embed = await create_punishment_embed(ActionType.BAN, author, action.reason, duration_label, issuer=bot_user, bot_user=bot_user)
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
                try:
                    await send_dm_to_user(author, build_dm_message(ActionType.KICK, guild.name, action.reason))
                except Exception:
                    logger.debug("Failed to DM user prior to kick, continuing with kick.")
                await guild.kick(author, reason=f"AI Mod: {action.reason}")
                embed = await create_punishment_embed(ActionType.KICK, author, action.reason, issuer=bot_user, bot_user=bot_user)
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
                try:
                    await send_dm_to_user(author, build_dm_message(ActionType.TIMEOUT, guild.name, action.reason, duration_label))
                except Exception:
                    logger.debug("Failed to DM user about timeout, continuing.")
                embed = await create_punishment_embed(ActionType.TIMEOUT, author, action.reason, duration_label, issuer=bot_user, bot_user=bot_user)
            except Exception as exc:
                logger.error("Failed to timeout user %s: %s", author.id, exc)
                return False
            

        case ActionType.WARN:
            try:
                try:
                    await send_dm_to_user(author, build_dm_message(ActionType.WARN, guild.name, action.reason))
                except Exception:
                    logger.debug("Failed to DM user for warning, continuing to post embed.")
                embed = await create_punishment_embed(ActionType.WARN, author, action.reason, issuer=bot_user, bot_user=bot_user)
            except Exception as exc:
                logger.error("Failed to process warn for user %s: %s", author.id, exc)
                return False
            

        case ActionType.UNBAN:
            try:
                embed = await create_punishment_embed(ActionType.UNBAN, author, action.reason, issuer=bot_user, bot_user=bot_user)
            except Exception as exc:
                logger.error("Failed to create unban embed for user %s: %s", author.id, exc)
                return False
        case _:
            pass

    if embed and isinstance(channel, (discord.TextChannel, discord.Thread)):
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            logger.warning("Missing permission to post embed in %s", getattr(channel, "name", channel))
        except Exception as exc:
            logger.error("Failed to send moderation embed: %s", exc)

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