"""
discord_utils.py
================

Low-level Discord utility functions for Modcord.
This module provides helpers for message deletion, DM sending, permission checks, and moderation action execution.
All logic here should be Discord-specific and stateless, suitable for use by higher-level bot logic.
"""


import datetime
from typing import Union

import discord

from modcord.util.logger import get_logger
from modcord.util.moderation_models import ActionData, ActionType, ModerationMessage

logger = get_logger("discord_utils")

# ==========================================
# Duration/constants and choices (moved here so discord_utils is self-contained)
# ==========================================

# Human-friendly label for a permanent duration
PERMANENT_DURATION = "Till the end of time"

DURATIONS = {
    "60 secs": 60,
    "5 mins": 5 * 60,
    "10 mins": 10 * 60,
    "30 mins": 30 * 60,
    "1 hour": 60 * 60,
    "2 hours": 2 * 60 * 60,
    "1 day": 24 * 60 * 60,
    "1 week": 7 * 24 * 60 * 60,
    PERMANENT_DURATION: 0,
}

DURATION_CHOICES = list(DURATIONS.keys())

DELETE_MESSAGE_CHOICES = [
    discord.OptionChoice(name="Don't Delete Any", value=0),
    discord.OptionChoice(name="Previous Hour", value=60 * 60),
    discord.OptionChoice(name="Previous 6 Hours", value=6 * 60 * 60),
    discord.OptionChoice(name="Previous 12 Hours", value=12 * 60 * 60),
    discord.OptionChoice(name="Previous 24 Hours", value=24 * 60 * 60),
    discord.OptionChoice(name="Previous 3 Days", value=3 * 24 * 60 * 60),
    discord.OptionChoice(name="Previous 7 Days", value=7 * 24 * 60 * 60),
]


# ==========================================
# Helpers copied from bot_helper (Discord-specific, safe to live here)
# ==========================================

def bot_can_manage_messages(channel: discord.TextChannel, guild: discord.Guild) -> bool:
    """
    Return whether the bot can read and delete messages in the given channel.
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
    Yield text channels where the bot has the required permissions.
    """
    for channel in getattr(guild, "text_channels", []):
        try:
            if bot_can_manage_messages(channel, guild):
                yield channel
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.debug(f"Skipping channel {getattr(channel, 'name', 'unknown')} due to error: {exc}")


# Shared sets for timeout-like actions
TIMEOUT_ACTIONS: set[ActionType] = {ActionType.TIMEOUT}



def is_ignored_author(self, author: Union[discord.User, discord.Member]) -> bool:
    """Return True if the author should be ignored (not discord member)."""
    return author.bot or not isinstance(author, discord.Member)


def build_dm_message(
    action: ActionType,
    guild_name: str,
    reason: str,
    duration_str: str | None = None,
) -> str:
    """Return the DM body for the given moderation action."""
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
    """Format a duration in seconds to a human-readable string."""
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


def parse_duration_to_seconds(human_readable_duration: str) -> int:
    """Convert a human-readable duration string to its equivalent in seconds."""
    return DURATIONS.get(human_readable_duration, 0)


async def create_punishment_embed(
    action_type: ActionType,
    user: discord.User | discord.Member,
    reason: str,
    duration_str: str | None = None,
    issuer: discord.User | discord.Member | discord.ClientUser | None = None,
    bot_user: discord.ClientUser | None = None
) -> discord.Embed:
    """Build a standardized embed for logging moderation actions."""
    action_details = {
        ActionType.BAN:     {"color": discord.Color.red(),    "emoji": "🔨", "label": "Ban"},
        ActionType.KICK:    {"color": discord.Color.orange(), "emoji": "👢", "label": "Kick"},
        ActionType.WARN:    {"color": discord.Color.yellow(), "emoji": "⚠️", "label": "Warn"},
        ActionType.TIMEOUT: {"color": discord.Color.blue(),   "emoji": "⏱️", "label": "Timeout"},
        ActionType.DELETE:  {"color": discord.Color.light_grey(), "emoji": "🗑️", "label": "Delete"},
        ActionType.UNBAN:   {"color": discord.Color.green(),  "emoji": "🔓", "label": "Unban"},
        ActionType.NULL:    {"color": discord.Color.light_grey(), "emoji": "❓", "label": "No Action"},
    }

    details = action_details.get(action_type, action_details[ActionType.NULL])
    label = details.get("label", str(action_type).capitalize())

    embed = discord.Embed(
        title=f"{details['emoji']} {label} Issued",
        color=details['color'],
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    embed.add_field(name="User", value=f"{user.mention} (`{user.id}`)", inline=True)
    embed.add_field(name="Action", value=label, inline=True)
    if issuer:
        embed.add_field(name="Moderator", value=issuer.mention, inline=True)

    embed.add_field(name="Reason", value=reason, inline=False)

    if duration_str and duration_str != PERMANENT_DURATION:
        duration_seconds = parse_duration_to_seconds(duration_str)
        if duration_seconds > 0:
            expire_time = discord.utils.utcnow() + datetime.timedelta(seconds=duration_seconds)
            embed.add_field(
                name="Duration",
                value=f"{duration_str} (Expires: <t:{int(expire_time.timestamp())}:R>)",
                inline=False,
            )
    elif duration_str:
        embed.add_field(name="Duration", value=duration_str, inline=False)

    embed.set_footer(text=f"Bot: {bot_user.name if bot_user else 'ModBot'}")
    return embed


async def delete_recent_messages(guild, member, seconds) -> int:
    """Delete recent messages from a member within a time window across channels."""
    if seconds <= 0:
        return 0

    window_start = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=seconds)
    deleted_count = 0

    for channel in iter_moderatable_channels(guild):
        try:
            async for message in channel.history(limit=100, after=window_start):
                if message.author.id != member.id:
                    continue

                if await safe_delete_message(message):
                    deleted_count += 1
        except discord.Forbidden:
            continue
        except Exception as exc:
            logger.error(f"Error deleting messages in {channel.name}: {exc}")

    return deleted_count


async def delete_messages_background(ctx: discord.ApplicationContext, user: discord.Member, delete_message_seconds: int):
    """Background helper to delete messages and notify the command issuer."""
    try:
        deleted = await delete_recent_messages(ctx.guild, user, delete_message_seconds)
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


from modcord.bot.unban_scheduler import (
    schedule_unban,
)

# --- Public Discord utility functions ---

async def safe_delete_message(message: discord.Message) -> bool:
    """
    Attempt to delete a Discord message, suppressing non-fatal errors.

    Args:
        message (discord.Message): The message to delete.

    Returns:
        bool: True if the message was deleted, False otherwise.
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
    Delete specific messages by their IDs across all text channels in the guild.

    Args:
        guild (discord.Guild): The guild to search for messages.
        message_ids (list[str]): List of message IDs to delete.

    Returns:
        int: Number of messages actually deleted.
    """
    if not message_ids:
        return 0
    try:
        pending_ids = {int(msg_id) for msg_id in message_ids}
    except (TypeError, ValueError):
        pending_ids = set()
        for raw_id in message_ids:
            try:
                pending_ids.add(int(raw_id))
            except (TypeError, ValueError):
                logger.warning(f"Skipping invalid message id: {raw_id}")
    deleted_count = 0
    for channel in iter_moderatable_channels(guild):
        if not pending_ids:
            break
        for message_id in list(pending_ids):
            try:
                message = await channel.fetch_message(message_id)
            except discord.NotFound:
                pending_ids.discard(message_id)
                continue
            except discord.Forbidden:
                logger.warning(f"No permission to fetch message {message_id} in {channel.name}")
                pending_ids.discard(message_id)
                continue
            except Exception as exc:
                logger.error(f"Error fetching message {message_id} in {channel.name}: {exc}")
                pending_ids.discard(message_id)
                continue
            if await safe_delete_message(message):
                deleted_count += 1
                logger.debug(f"Deleted message {message_id} from channel {channel.name}")
            pending_ids.discard(message_id)
    if pending_ids:
        logger.debug(f"Failed to locate messages: {sorted(pending_ids)}")
    return deleted_count


async def delete_recent_messages_by_count(guild: discord.Guild, member: discord.Member, count: int) -> int:
    """
    Delete the most recent messages from a user up to the specified count across all text channels.

    Args:
        guild (discord.Guild): The guild to search for messages.
        member (discord.Member): The member whose messages to delete.
        count (int): Maximum number of messages to delete.

    Returns:
        int: Number of messages actually deleted.
    """
    if count <= 0:
        return 0
    deleted_count = 0
    for channel in iter_moderatable_channels(guild):
        if deleted_count >= count:
            break
        fetch_limit = min(50, max(count - deleted_count, 1))
        try:
            async for message in channel.history(limit=fetch_limit):
                if message.author != member:
                    continue
                if await safe_delete_message(message):
                    deleted_count += 1
                if deleted_count >= count:
                    break
        except discord.Forbidden:
            continue  # No access to this channel
        except Exception as exc:
            logger.error(f"Error processing channel {channel.name}: {exc}")
    return deleted_count


async def send_dm_to_user(target_user: discord.Member, message_content: str) -> bool:
    """
    Attempt to send a direct message (DM) to a user.

    Args:
        target_user (discord.Member): The user to DM.
        message_content (str): The message content.

    Returns:
        bool: True if DM sent successfully, False otherwise.
    """
    try:
        await target_user.send(message_content)
        return True
    except discord.Forbidden:
        logger.info(f"Could not DM {target_user.display_name}: They may have DMs disabled.")
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
    Send a DM to the user and an embed to the channel.

    Args:
        ctx (discord.ApplicationContext): The context of the command.
        user (discord.Member): The user to send the DM to.
        action_type (ActionType): The type of moderation action.
        reason (str): The reason for the action.
        duration_str (str | None): The duration of the action, if applicable.
    """
    dm_message = build_dm_message(action_type, ctx.guild.name, reason, duration_str)
    if not dm_message:
        dm_message = f"You have been {action_type.value}ed in {ctx.guild.name}.\n**Reason**: {reason}"
    await send_dm_to_user(user, dm_message)
    embed = await create_punishment_embed(action_type, user, reason, duration_str, bot_user=ctx.bot.user)
    await ctx.followup.send(embed=embed)


def has_permissions(application_context: discord.ApplicationContext, **required_permissions) -> bool:
    """
    Check if the command issuer has the required permissions.

    Args:
        application_context (discord.ApplicationContext): The context of the command.
        **required_permissions: The permissions to check (e.g., manage_messages=True).

    Returns:
        bool: True if the user has permissions, False otherwise.
    """
    if not isinstance(application_context.author, discord.Member):
        return False
    return all(getattr(application_context.author.guild_permissions, permission_name, False) for permission_name in required_permissions)


# --- Main moderation action entry point ---

async def apply_action_decision(
    action: ActionData,
    pivot: ModerationMessage,
    bot_user: discord.ClientUser,
    bot_client: discord.Client,
) -> bool:
    """
    Execute a moderation decision produced by the AI pipeline.

    Args:
        action (ActionData): The action to apply.
        pivot (ModerationMessage): The message that triggered the action.
        bot_user (discord.ClientUser): The bot's user object (for embeds).
        bot_client (discord.Client): The bot client instance (for scheduling unbans).

    Returns:
        bool: True if action was applied successfully, False otherwise.
    """
    if action.action is ActionType.NULL:
        logger.debug("Ignoring null moderation action for user %s", action.user_id)
        return True
    discord_message = pivot.discord_message
    if discord_message is None:
        logger.warning("No Discord message object for moderation pivot %s; skipping action", pivot.message_id)
        return False
    guild = discord_message.guild
    author = discord_message.author
    if guild is None or not isinstance(author, discord.Member):
        logger.debug("Skipping action %s; missing guild or non-member author", action.action.value)
        return False
    channel = discord_message.channel
    logger.info(
        "Executing %s on user %s (%s) for reason '%s'", action.action.value, author.display_name, author.id, action.reason
    )
    try:
        await safe_delete_message(discord_message)
    except Exception as exc:
        logger.warning("Failed to delete pivot message %s: %s", discord_message.id, exc)
    message_ids = {mid for mid in (action.message_ids or []) if mid}
    pivot_id = str(discord_message.id)
    message_ids.discard(pivot_id)
    if message_ids:
        try:
            deleted_count = await delete_messages_by_ids(guild, list(message_ids))
            logger.debug("Deleted %s referenced messages for user %s", deleted_count, author.display_name)
        except Exception as exc:
            logger.error("Failed to delete referenced messages %s: %s", sorted(message_ids), exc)
    if action.action is ActionType.DELETE:
        return True
    embed: discord.Embed | None = None
    success = True
    if action.action is ActionType.BAN:
        duration_seconds = int(action.ban_duration or 0)
        is_permanent = duration_seconds <= 0
        duration_label = PERMANENT_DURATION if is_permanent else format_duration(duration_seconds)
        try:
            await send_dm_to_user(author, build_dm_message(ActionType.BAN, guild.name, action.reason, duration_label))
        except Exception:
            logger.debug("Failed to DM user prior to ban, continuing with ban.")
        try:
            await guild.ban(author, reason=f"AI Mod: {action.reason}")
            embed = await create_punishment_embed(ActionType.BAN, author, action.reason, duration_label, issuer=bot_user, bot_user=bot_user)
        except Exception as exc:
            logger.error("Failed to ban user %s: %s", author.id, exc, exc_info=True)
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
                logger.error("Failed to schedule unban for user %s: %s", author.id, exc, exc_info=True)
                success = False
    elif action.action is ActionType.KICK:
        try:
            try:
                await send_dm_to_user(author, build_dm_message(ActionType.KICK, guild.name, action.reason))
            except Exception:
                logger.debug("Failed to DM user prior to kick, continuing with kick.")
            await guild.kick(author, reason=f"AI Mod: {action.reason}")
            embed = await create_punishment_embed(ActionType.KICK, author, action.reason, issuer=bot_user, bot_user=bot_user)
        except Exception as exc:
            logger.error("Failed to kick user %s: %s", author.id, exc, exc_info=True)
            return False
    elif action.action is ActionType.TIMEOUT:
        duration_seconds = action.timeout_duration if action.timeout_duration is not None else 10 * 60
        if duration_seconds <= 0:
            duration_seconds = 10 * 60
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
            logger.error("Failed to timeout user %s: %s", author.id, exc, exc_info=True)
            return False
    elif action.action is ActionType.WARN:
        try:
            try:
                await send_dm_to_user(author, build_dm_message(ActionType.WARN, guild.name, action.reason))
            except Exception:
                logger.debug("Failed to DM user for warning, continuing to post embed.")
            embed = await create_punishment_embed(ActionType.WARN, author, action.reason, issuer=bot_user, bot_user=bot_user)
        except Exception as exc:
            logger.error("Failed to process warn for user %s: %s", author.id, exc, exc_info=True)
            return False
    elif action.action is ActionType.UNBAN:
        try:
            embed = await create_punishment_embed(ActionType.UNBAN, author, action.reason, issuer=bot_user, bot_user=bot_user)
        except Exception as exc:
            logger.error("Failed to create unban embed for user %s: %s", author.id, exc, exc_info=True)
            return False
    if embed and isinstance(channel, (discord.TextChannel, discord.Thread)):
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            logger.warning("Missing permission to post embed in %s", getattr(channel, "name", channel))
        except Exception as exc:
            logger.error("Failed to send moderation embed: %s", exc)
    return success
