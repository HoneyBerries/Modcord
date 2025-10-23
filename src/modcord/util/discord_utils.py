"""
discord_utils.py
================

Low-level Discord utility functions for Modcord.
This module provides helpers for message deletion, DM sending, permission checks, and moderation action execution.
All logic here should be Discord-specific and stateless, suitable for use by higher-level bot logic.
"""


import datetime
from typing import Mapping, Union

import discord

from modcord.util.logger import get_logger
from modcord.moderation.moderation_datatypes import ActionData, ActionType, ModerationMessage

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
    """Check whether the bot can read and delete messages in ``channel``.

    Parameters
    ----------
    channel:
        Text channel to inspect for message management permissions.
    guild:
        Guild used to resolve the bot's member object and permission set.

    Returns
    -------
    bool
        ``True`` when the bot may read and manage messages in ``channel``.
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
    """Yield text channels where the bot can manage messages safely.

    Parameters
    ----------
    guild:
        Guild whose text channels should be inspected.

    Yields
    ------
    discord.TextChannel
        Channels that are safe for moderation operations.
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
    """Return ``True`` when ``author`` should be ignored by moderation handlers.

    Parameters
    ----------
    author:
        User or member who produced the event.

    Returns
    -------
    bool
        ``True`` for bot accounts or non-member authors.
    """
    return author.bot or not isinstance(author, discord.Member)


def has_elevated_permissions(member: Union[discord.User, discord.Member]) -> bool:
    """Return ``True`` for members holding moderator-level privileges.

    Parameters
    ----------
    member:
        Candidate whose guild permissions are evaluated.

    Returns
    -------
    bool
        ``True`` when the member has administrator/manage guild/moderate members.
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
    """Construct a moderator DM body tailored to the ``action``.

    Parameters
    ----------
    action:
        Moderation action that triggered the notification.
    guild_name:
        Name of the guild where the action occurred.
    reason:
        Human-friendly reason associated with the action.
    duration_str:
        Optional duration label used for timeouts or temporary bans.

    Returns
    -------
    str
        DM payload ready for transmission to the affected user.
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
    """Return a human-readable string representation of ``seconds``."""
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
    """Convert a human-readable duration into its total seconds payload."""
    return DURATIONS.get(human_readable_duration, 0)


async def create_punishment_embed(
    action_type: ActionType,
    user: discord.User | discord.Member,
    reason: str,
    duration_str: str | None = None,
    issuer: discord.User | discord.Member | discord.ClientUser | None = None,
    bot_user: discord.ClientUser | None = None
) -> discord.Embed:
    """Build a standardized embed summarizing a moderation action.

    Parameters
    ----------
    action_type:
        Type of moderation action that occurred.
    user:
        Target user that the action applied to.
    reason:
        Explanation to surface in logs and embeds.
    duration_str:
        Optional duration label for temporary actions.
    issuer:
        Moderator responsible for the action, if known.
    bot_user:
        Bot user reference used for footer labeling.

    Returns
    -------
    discord.Embed
        Embed object ready for dispatch to a text channel.
    """
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
    """Delete recent messages from ``member`` across moderatable channels.

    Parameters
    ----------
    guild:
        Guild providing the channels to inspect for messages.
    member:
        Target member whose messages should be removed.
    seconds:
        Lookback window expressed in seconds.

    Returns
    -------
    int
        Count of successfully deleted messages.
    """
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
    """Delete messages in the background and report the outcome to the invoker.

    Parameters
    ----------
    ctx:
        Command context used for follow-up messaging.
    user:
        Guild member whose messages should be deleted.
    delete_message_seconds:
        Time window in seconds to inspect for deletions.
    """
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
    """Delete ``message`` while suppressing recoverable Discord errors.

    Parameters
    ----------
    message:
        Discord message slated for deletion.

    Returns
    -------
    bool
        ``True`` when deletion succeeds, otherwise ``False``.
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
    """Delete specific messages cross-channel using their identifiers.

    Parameters
    ----------
    guild:
        Guild whose text channels should be searched.
    message_ids:
        Collection of Discord message identifiers to delete.

    Returns
    -------
    int
        Number of messages successfully removed.
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
    """Delete the most recent ``count`` messages from ``member``.

    Parameters
    ----------
    guild:
        Guild whose text channels will be scanned.
    member:
        Member whose recent messages should be purged.
    count:
        Maximum number of messages to remove.

    Returns
    -------
    int
        Number of messages deleted successfully.
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
    """Attempt to send a direct message to ``target_user``.

    Parameters
    ----------
    target_user:
        Member who should receive the DM.
    message_content:
        Text body of the DM message.

    Returns
    -------
    bool
        ``True`` when the DM is dispatched successfully.
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
    """Notify moderators and the affected user about an action.

    Parameters
    ----------
    ctx:
        Slash command context used for follow-up messaging.
    user:
        Member receiving the DM notification.
    action_type:
        Moderation action type applied to the member.
    reason:
        Rationale that should be surfaced in notifications.
    duration_str:
        Optional duration label for temporary actions.
    """
    dm_message = build_dm_message(action_type, ctx.guild.name, reason, duration_str)
    if not dm_message:
        dm_message = f"You have been {action_type.value}ed in {ctx.guild.name}.\n**Reason**: {reason}"
    await send_dm_to_user(user, dm_message)
    embed = await create_punishment_embed(action_type, user, reason, duration_str, bot_user=ctx.bot.user)
    await ctx.followup.send(embed=embed)


def has_permissions(application_context: discord.ApplicationContext, **required_permissions) -> bool:
    """Return ``True`` when the command issuer holds the requested permissions.

    Parameters
    ----------
    application_context:
        Slash command context for the invocation.
    **required_permissions:
        Keyword permission flags to verify on the invoking member.

    Returns
    -------
    bool
        ``True`` if each permission flag evaluates to ``True``.
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
    *,
    message_lookup: Mapping[str, discord.Message] | None = None,
) -> bool:
    """Execute a moderation decision produced by the AI pipeline.

    Parameters
    ----------
    action:
        Moderation action recommended by the AI.
    pivot:
        Original moderation message that triggered the response.
    bot_user:
        Bot user reference used for embed authoring.
    bot_client:
        Discord client used for follow-up actions (e.g., scheduling unbans).

    Returns
    -------
    bool
        ``True`` when the action was applied without critical errors.
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
    logger.debug(
        "Executing %s on user %s (%s) for reason '%s'", action.action.value, author.display_name, author.id, action.reason
    )
    try:
        await safe_delete_message(discord_message)
    except Exception as exc:
        logger.warning("Failed to delete pivot message %s: %s", discord_message.id, exc)
    raw_ids = [mid for mid in (action.message_ids or []) if mid]
    pivot_id = str(discord_message.id)
    filtered_ids = [mid for mid in raw_ids if mid != pivot_id]
    if filtered_ids:
        cached_messages = message_lookup or {}
        delete_queue: list[str] = []
        deleted_total = 0
        for mid in filtered_ids:
            cached = cached_messages.get(mid)
            if cached is None:
                delete_queue.append(mid)
                continue
            if await safe_delete_message(cached):
                deleted_total += 1
            else:
                delete_queue.append(mid)

        if delete_queue:
            try:
                deleted_total += await delete_messages_by_ids(guild, delete_queue)
            except Exception as exc:
                logger.error("Failed to delete referenced messages %s: %s", sorted(delete_queue), exc)
            else:
                logger.debug("Deleted %s referenced messages for user %s", deleted_total, author.display_name)
        else:
            logger.debug("Deleted %s referenced messages for user %s", deleted_total, author.display_name)
    if action.action is ActionType.DELETE:
        return True
    embed: discord.Embed | None = None
    success = True
    if action.action is ActionType.BAN:
        # ban_duration is in minutes: 0 = not applicable, -1 = permanent, positive = temporary
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
    elif action.action is ActionType.KICK:
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
    elif action.action is ActionType.TIMEOUT:
        # timeout_duration is in minutes: 0 = not applicable, -1 = permanent (capped to Discord's 28-day max), positive = temporary
        duration_minutes = action.timeout_duration if action.timeout_duration is not None else 0
        if duration_minutes == 0:
            logger.debug("Timeout duration is 0 (not applicable); skipping timeout for user %s", action.user_id)
            return True
        # Discord max timeout is 28 days; treat -1 as that max
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
    elif action.action is ActionType.WARN:
        try:
            try:
                await send_dm_to_user(author, build_dm_message(ActionType.WARN, guild.name, action.reason))
            except Exception:
                logger.debug("Failed to DM user for warning, continuing to post embed.")
            embed = await create_punishment_embed(ActionType.WARN, author, action.reason, issuer=bot_user, bot_user=bot_user)
        except Exception as exc:
            logger.error("Failed to process warn for user %s: %s", author.id, exc)
            return False
    elif action.action is ActionType.UNBAN:
        try:
            embed = await create_punishment_embed(ActionType.UNBAN, author, action.reason, issuer=bot_user, bot_user=bot_user)
        except Exception as exc:
            logger.error("Failed to create unban embed for user %s: %s", author.id, exc)
            return False
    if embed and isinstance(channel, (discord.TextChannel, discord.Thread)):
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            logger.warning("Missing permission to post embed in %s", getattr(channel, "name", channel))
        except Exception as exc:
            logger.error("Failed to send moderation embed: %s", exc)
    return success
