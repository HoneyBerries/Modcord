"""
Bot Helper Functions
===================

This module provides helper functions for the Discord Moderation Bot.
"""
import asyncio
import datetime
import heapq
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import discord

from modcord.util.actions import ActionType
from modcord.util.logger import get_logger
from modcord.bot.bot_settings import bot_settings

# Get logger for this module
logger = get_logger("bot_helper")

# ==========================================
# Constants
# ==========================================

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
# Internal Helpers
# ==========================================

def _bot_can_manage_messages(channel: discord.TextChannel, guild: discord.Guild) -> bool:
    """Return whether the bot can read and delete messages in the given channel."""
    me = getattr(guild, "me", None)
    if me is None:
        return True

    try:
        permissions = channel.permissions_for(me)
    except Exception:  # pragma: no cover - discord internals guard
        return False

    return permissions.read_messages and permissions.manage_messages


def _iter_moderatable_channels(guild: discord.Guild):
    """Yield text channels where the bot has the required permissions."""
    for channel in getattr(guild, "text_channels", []):
        try:
            if _bot_can_manage_messages(channel, guild):
                yield channel
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.debug(f"Skipping channel {getattr(channel, 'name', 'unknown')} due to error: {exc}")


async def _safe_delete_message(message: discord.Message) -> bool:
    """Attempt to delete a message, suppressing non-fatal errors."""
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


# Shared sets for timeout-like actions
TIMEOUT_ACTIONS: set[ActionType] = {ActionType.TIMEOUT}


def _build_dm_message(
    action: ActionType,
    guild_name: str,
    reason: str,
    duration_str: str | None = None,
) -> str:
    """Return the DM body for the given action."""
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


# ==========================================
# Utility Functions
# ==========================================

def format_duration(seconds: int) -> str:
    """
    Format a duration in seconds to a human-readable string.
    
    Args:
        seconds (int): Duration in seconds
        
    Returns:
        str: Formatted duration string (e.g., "5 mins", "1 hour", "2 days")
    """
    if seconds == 0:
        return PERMANENT_DURATION
    elif seconds < 60:
        return f"{seconds} secs"
    elif seconds < 3600:  # Less than 1 hour
        mins = seconds // 60
        return f"{mins} mins"
    elif seconds < 86400:  # Less than 1 day
        hours = seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''}"
    else:  # 1 day or more
        days = seconds // 86400
        return f"{days} day{'s' if days != 1 else ''}"


async def delete_recent_messages_by_count(guild: discord.Guild, member: discord.Member, count: int) -> int:
    """
    Delete the most recent messages from a user up to the specified count.
    
    Args:
        guild (discord.Guild): The guild to search for messages
        member (discord.Member): The member whose messages to delete
        count (int): Maximum number of messages to delete
        
    Returns:
        int: Number of messages actually deleted
    """
    if count <= 0:
        return 0

    deleted_count = 0

    for channel in _iter_moderatable_channels(guild):
        if deleted_count >= count:
            break

        fetch_limit = min(50, max(count - deleted_count, 1))
        try:
            async for message in channel.history(limit=fetch_limit):
                if message.author != member:
                    continue

                if await _safe_delete_message(message):
                    deleted_count += 1

                if deleted_count >= count:
                    break
        except discord.Forbidden:
            continue  # No access to this channel
        except Exception as exc:
            logger.error(f"Error processing channel {channel.name}: {exc}")

    return deleted_count


async def delete_messages_by_ids(guild: discord.Guild, message_ids: list[str]) -> int:
    """
    Delete specific messages by their IDs across all channels in the guild.
    
    Args:
        guild (discord.Guild): The guild to search for messages
        message_ids (list[str]): List of message IDs to delete
        
    Returns:
        int: Number of messages actually deleted
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

    for channel in _iter_moderatable_channels(guild):
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

            if await _safe_delete_message(message):
                deleted_count += 1
                logger.debug(f"Deleted message {message_id} from channel {channel.name}")

            pending_ids.discard(message_id)

    if pending_ids:
        logger.debug(f"Failed to locate messages: {sorted(pending_ids)}")

    return deleted_count


def has_permissions(application_context: discord.ApplicationContext, **required_permissions) -> bool:
    """
    Check if the command issuer has the required permissions.

    Args:
        application_context (discord.ApplicationContext): The context of the command.
        **required_permissions: The permissions to check.

    Returns:
        bool: True if the user has permissions, False otherwise.
    """
    if not isinstance(application_context.author, discord.Member):
        return False
    return all(getattr(application_context.author.guild_permissions, permission_name, False) for permission_name in required_permissions)


def parse_duration_to_seconds(human_readable_duration: str) -> int:
    """
    Convert a human-readable duration string to its equivalent in seconds.

    Args:
        human_readable_duration (str): The duration string to parse.

    Returns:
        int: The duration in seconds, or 0 if permanent or unrecognized.
    """
    return DURATIONS.get(human_readable_duration, 0)


async def send_dm_to_user(target_user: discord.Member, message_content: str) -> bool:
    """
    Attempt to send a direct message to a user.

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
        # User may have DMs disabled or bot blocked.
        logger.info(f"Could not DM {target_user.display_name}: They may have DMs disabled.")
    except Exception as e:
        logger.error(f"Failed to send DM to {target_user.display_name}: {e}")
    return False


# ==========================================
# Embed Builder
# ==========================================

async def create_punishment_embed(
    action_type: ActionType,
    user: discord.User | discord.Member,
    reason: str,
    duration_str: str | None = None,
    issuer: discord.User | discord.Member | discord.ClientUser | None = None,
    bot_user: discord.ClientUser | None = None
) -> discord.Embed:
    """
    Build a standardized embed for logging moderation actions.

    Args:
        action_type (ActionType): Type of moderation action (enum).
        user (discord.User | discord.Member): Target user.
        reason (str): Reason for action.
        duration_str (str | None): Duration string, if applicable.
        issuer (discord.User | discord.Member | discord.ClientUser | None): Moderator issuing the action.
        bot_user (discord.ClientUser | None): Bot user for footer.

    Returns:
        discord.Embed: The constructed embed.
    """
    # Define colors and emojis for different actions to provide quick visual cues.
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

    # Add duration field if applicable and not permanent.
    if duration_str and duration_str != PERMANENT_DURATION:
        duration_seconds = parse_duration_to_seconds(duration_str)
        if duration_seconds > 0:
            expire_time = discord.utils.utcnow() + datetime.timedelta(seconds=duration_seconds)
            embed.add_field(
                name="Duration",
                value=f"{duration_str} (Expires: <t:{int(expire_time.timestamp())}:R>)",
                inline=False
            )
    elif duration_str: # Handles "Till the end of time"
        embed.add_field(name="Duration", value=duration_str, inline=False)

    embed.set_footer(text=f"Bot: {bot_user.name if bot_user else 'ModBot'}")
    return embed


# ==========================================
# Moderation Action Handler
# ==========================================

async def handle_error(ctx: discord.ApplicationContext, error: Exception):
    """
    Handle common errors in moderation commands.

    Args:
        ctx (discord.ApplicationContext): The context of the command.
        error (Exception): The error that occurred.
    """
    if isinstance(error, discord.Forbidden):
        await ctx.followup.send("I do not have permissions to perform this action.", ephemeral=True)
    elif isinstance(error, AttributeError):
        await ctx.followup.send("Failed: Target is not a valid server member.", ephemeral=True)
    else:
        logger.error(f"An unexpected error occurred: {error}", exc_info=True)
        await ctx.followup.send("An unexpected error occurred.", ephemeral=True)


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
        action_type (ActionType): The type of action being taken.
        reason (str): The reason for the action.
        duration_str (str | None): The duration of the action, if applicable.
    """
    dm_message = _build_dm_message(action_type, ctx.guild.name, reason, duration_str)
    if not dm_message:
        dm_message = f"You have been {action_type.value}ed in {ctx.guild.name}.\n**Reason**: {reason}"

    await send_dm_to_user(user, dm_message)

    # Create and send embed
    embed = await create_punishment_embed(action_type, user, reason, duration_str, bot_user=ctx.bot.user)
    await ctx.followup.send(embed=embed)



async def take_action(action: ActionType, reason: str, message: discord.Message, bot_user: discord.ClientUser | None = None):
    """
    Applies a disciplinary action to the author of a message based on AI output.
    This function is designed for automated actions.

    Args:
        action (ActionType): The moderation action to take.
        reason (str): Reason for the action.
        message (discord.Message): The message triggering the action.
        bot_user (discord.ClientUser | None): Bot user for embeds.

    Returns:
        None
    """
    await take_batch_action(
        action=action,
        reason=reason,
        message=message,
        bot_user=bot_user,
        message_ids=[str(message.id)] if action == ActionType.DELETE else None,
        timeout_duration=None,
        ban_duration=None
    )


async def take_batch_action(
    action: ActionType, 
    reason: str, 
    message: discord.Message, 
    bot_user: discord.ClientUser | None = None,
    *,
    message_ids: list[str] | None = None,
    timeout_duration: int | None = None,
    ban_duration: int | None = None
):
    """
    Applies a disciplinary action with batch-specific parameters.
    This is the enhanced version that supports the new batch processing parameters.

    Args:
        action (ActionType): The moderation action to take.
        reason (str): Reason for the action.
        message (discord.Message): The message triggering the action.
        bot_user (discord.ClientUser | None): Bot user for embeds.
        message_ids (list[str] | None): Specific message IDs to delete before the action.
        timeout_duration (int | None): Timeout duration in seconds.
        ban_duration (int | None): Ban duration in seconds (0 or None = permanent).

    Returns:
        None
    """
    # Ignore if action is null, or message/guild/user is invalid.
    if action == ActionType.NULL or not message.guild or not isinstance(message.author, discord.Member):
        return

    user = message.author
    guild = message.guild
    channel = message.channel

    logger.info(f"AI batch action triggered: '{action.value}' on user {user.display_name} for reason: '{reason}' (message_ids={message_ids}, timeout_duration={timeout_duration}, ban_duration={ban_duration})")

    try:
        # Always attempt to remove the triggering message.
        await _safe_delete_message(message)

        # Handle message deletion first if specified
        if message_ids:
            try:
                deleted_count = await delete_messages_by_ids(guild, message_ids)
                logger.info(f"Deleted {deleted_count} specific messages from {user.display_name}")
            except Exception as e:
                logger.error(f"Failed to delete messages {message_ids} from {user.display_name}: {e}")

        if action == ActionType.DELETE:
            # DELETE action only deletes messages, handled above
            return

        # Prepare DM and embed for other actions.
        embed: discord.Embed | None = None
        duration_str: str | None = None

        if action == ActionType.BAN:
            # Use ban_duration if specified
            is_permanent = ban_duration is None or ban_duration == 0
            duration_seconds = 0 if is_permanent else int(ban_duration or 0)
            duration_str = PERMANENT_DURATION if is_permanent else format_duration(duration_seconds)

            await send_dm_to_user(user, _build_dm_message(ActionType.BAN, guild.name, reason, duration_str))
            await guild.ban(user, reason=f"AI Mod: {reason}")
            embed = await create_punishment_embed(ActionType.BAN, user, reason, duration_str, bot_user, bot_user)
            
            # Schedule unban if temporary
            if not is_permanent:
                await schedule_unban(
                    guild=guild,
                    user_id=user.id,
                    channel=channel,
                    duration_seconds=ban_duration if ban_duration is not None else 0,
                    bot=None,
                )

        elif action == ActionType.KICK:
            await send_dm_to_user(user, _build_dm_message(ActionType.KICK, guild.name, reason))
            await guild.kick(user, reason=f"AI Mod: {reason}")
            embed = await create_punishment_embed(ActionType.KICK, user, reason, issuer=bot_user, bot_user=bot_user)

        elif action == ActionType.TIMEOUT:
            # Use timeout_duration if specified, otherwise default to 10 minutes
            duration_seconds = timeout_duration if timeout_duration is not None else 10 * 60
            duration_str = format_duration(duration_seconds)
            until = discord.utils.utcnow() + datetime.timedelta(seconds=duration_seconds)
            
            await user.timeout(until, reason=f"AI Mod: {reason}")
            await send_dm_to_user(user, _build_dm_message(ActionType.TIMEOUT, guild.name, reason, duration_str))
            embed = await create_punishment_embed(ActionType.TIMEOUT, user, reason, duration_str, bot_user, bot_user)

        elif action == ActionType.WARN:
            await send_dm_to_user(user, _build_dm_message(ActionType.WARN, guild.name, reason))
            embed = await create_punishment_embed(ActionType.WARN, user, reason, issuer=bot_user, bot_user=bot_user)

        elif action == ActionType.UNBAN:
            embed = await create_punishment_embed(ActionType.UNBAN, user, reason, issuer=bot_user, bot_user=bot_user)

        # Send embed to channel if possible.
        if embed and isinstance(channel, (discord.TextChannel, discord.Thread)):
            await channel.send(embed=embed)

    except discord.Forbidden:
        logger.warning(f"Failed to execute '{action.value}' on {user.display_name}: Missing permissions.")
    except Exception as e:
        logger.error(f"Error executing action '{action.value}' on {user.display_name}: {e}", exc_info=True)


# ==========================================
# Scheduled Unban Helper
# ==========================================

@dataclass
class _ScheduledUnban:
    guild: discord.Guild
    user_id: int
    channel: Optional[discord.abc.Messageable]
    bot: Optional[discord.Client]
    reason: str = "Ban duration expired."


class UnbanScheduler:
    """Central scheduler that coordinates delayed unban tasks without spawning excess tasks."""

    def __init__(self) -> None:
        self._heap: list[tuple[float, int, _ScheduledUnban]] = []
        self._pending_keys: Dict[Tuple[int, int], int] = {}
        self._cancelled_ids: set[int] = set()
        self._counter: int = 0
        self._runner_task: asyncio.Task[None] | None = None
        self._condition: asyncio.Condition = asyncio.Condition()

    def _ensure_runner(self) -> None:
        loop = asyncio.get_running_loop()
        if self._runner_task is None or self._runner_task.done():
            self._runner_task = loop.create_task(self._run(), name="modcord-unban-scheduler")

    async def schedule(
        self,
        guild: discord.Guild,
        user_id: int,
        channel: Optional[discord.abc.Messageable],
        duration_seconds: float,
        bot: Optional[discord.Client],
        *,
        reason: str = "Ban duration expired."
    ) -> None:
        """Schedule an unban. Replaces any existing pending unban for the same user in the same guild."""

        payload = _ScheduledUnban(guild=guild, user_id=user_id, channel=channel, bot=bot, reason=reason)

        if duration_seconds <= 0:
            await self._execute(payload)
            return

        loop = asyncio.get_running_loop()
        run_at = loop.time() + duration_seconds

        async with self._condition:
            self._ensure_runner()
            key = (guild.id, user_id)
            if key in self._pending_keys:
                self._cancelled_ids.add(self._pending_keys[key])

            self._counter += 1
            job_id = self._counter
            heapq.heappush(self._heap, (run_at, job_id, payload))
            self._pending_keys[key] = job_id
            self._condition.notify_all()

    async def cancel(self, guild_id: int, user_id: int) -> bool:
        """Cancel a pending unban task if present."""

        async with self._condition:
            key = (guild_id, user_id)
            job_id = self._pending_keys.pop(key, None)
            if job_id is None:
                return False

            self._cancelled_ids.add(job_id)
            self._condition.notify_all()
            return True

    async def shutdown(self) -> None:
        """Stop the scheduler task and clear pending work. Useful for tests."""

        async with self._condition:
            if self._runner_task:
                self._runner_task.cancel()
            self._heap.clear()
            self._pending_keys.clear()
            self._cancelled_ids.clear()
            self._condition.notify_all()

        if self._runner_task:
            try:
                await self._runner_task
            except asyncio.CancelledError:
                pass
            finally:
                self._runner_task = None

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            async with self._condition:
                while True:
                    if not self._heap:
                        await self._condition.wait()
                        continue

                    run_at, job_id, payload = self._heap[0]

                    if job_id in self._cancelled_ids:
                        heapq.heappop(self._heap)
                        self._cancelled_ids.remove(job_id)
                        self._pending_keys.pop((payload.guild.id, payload.user_id), None)
                        continue

                    delay = run_at - loop.time()
                    if delay > 0:
                        try:
                            await asyncio.wait_for(self._condition.wait(), timeout=delay)
                        except asyncio.TimeoutError:
                            pass
                        continue

                    heapq.heappop(self._heap)
                    self._pending_keys.pop((payload.guild.id, payload.user_id), None)
                    task_payload = payload
                    break

            try:
                await self._execute(task_payload)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(f"Failed to auto-unban user {task_payload.user_id}: {exc}", exc_info=True)

    async def _execute(self, payload: _ScheduledUnban) -> None:
        guild = payload.guild
        user_id = payload.user_id

        try:
            user_obj = discord.Object(id=user_id)
            await guild.unban(user_obj, reason=payload.reason)
            logger.info(f"Unbanned user {user_id} after ban expired.")

            if payload.bot and isinstance(payload.channel, (discord.TextChannel, discord.Thread)):
                try:
                    user = await payload.bot.fetch_user(user_id)
                    embed = await create_punishment_embed(
                        ActionType.UNBAN,
                        user,
                        payload.reason,
                        issuer=payload.bot.user,
                        bot_user=payload.bot.user,
                    )
                    await payload.channel.send(embed=embed)
                except Exception as e:  # noqa: BLE001 - log and continue
                    logger.warning(f"Could not send unban notification for {user_id}: {e}")

        except discord.NotFound:
            logger.warning(f"Could not unban user {user_id}: User not found in ban list.")
        except Exception as e:  # noqa: BLE001 - propagate failure via log only
            logger.error(f"Failed to auto-unban user {user_id}: {e}")


_UNBAN_SCHEDULER = UnbanScheduler()


async def schedule_unban(
    guild: discord.Guild,
    user_id: int,
    channel: Optional[discord.abc.Messageable],
    duration_seconds: float,
    bot: Optional[discord.Client],
    *,
    reason: str = "Ban duration expired."
) -> None:
    """Public helper to schedule a user unban via the shared scheduler."""

    await _UNBAN_SCHEDULER.schedule(
        guild=guild,
        user_id=user_id,
        channel=channel,
        duration_seconds=duration_seconds,
        bot=bot,
        reason=reason,
    )


async def unban_later(
    guild: discord.Guild,
    user_id: int,
    channel: discord.abc.Messageable | None,
    duration_seconds: float,
    bot: Optional[discord.Client],
) -> None:
    """Backward-compatible alias for schedule_unban."""

    await schedule_unban(guild, user_id, channel, duration_seconds, bot)


async def cancel_scheduled_unban(guild_id: int, user_id: int) -> bool:
    """Cancel a pending unban if one exists."""

    return await _UNBAN_SCHEDULER.cancel(guild_id, user_id)


async def reset_unban_scheduler_for_tests() -> None:
    """Reset the unban scheduler. Intended for test isolation only."""

    global _UNBAN_SCHEDULER
    await _UNBAN_SCHEDULER.shutdown()
    _UNBAN_SCHEDULER = UnbanScheduler()


# ==========================================
# Server Rules Management
# ==========================================


# Expose the rule channel regex pattern for use in other modules
import re
rule_channel_pattern = re.compile(r"(guidelines|regulations|policy|policies|server[-_]?rules|rules)", re.IGNORECASE)

async def fetch_server_rules_from_channel(guild: discord.Guild) -> str:
    """
    Fetches server rules from channels that contain rule-related keywords.

    Args:
        guild (discord.Guild): The guild to scan for rule channels.

    Returns:
        str: Combined rules text from all found channels.
    """
    # Use the shared rule_channel_pattern

    messages = []
    for channel in guild.text_channels:
        if rule_channel_pattern.search(channel.name):
            try:
                async for message in channel.history(oldest_first=True):
                    if message.content.strip():
                        messages.append(message.content.strip())
                    for embed in message.embeds:
                        if embed.description:
                            messages.append(embed.description.strip())
                        for field in embed.fields:
                            if field.value:
                                messages.append(f"{field.name}: {field.value}".strip())

            except discord.Forbidden:
                logger.warning(f"No permission to read rules channel: {channel.name} in {guild.name}")
            except Exception as e:
                logger.warning(f"Error fetching rules from channel {channel.name} in {guild.name}: {e}")
    if messages and len(messages) > 0:
        rules_text = "\n\n".join(messages)
        logger.debug(f"Successfully fetched {len(messages)} rule messages from all rule channels")
        return rules_text
    
    logger.warning(f"No rules channel found in {guild.name}")
    return ""


async def refresh_rules_cache(bot, server_rules_cache: dict):
    """
    Periodically refresh the server rules cache for all guilds.

    Args:
        bot: The Discord bot instance.
        server_rules_cache (dict): Cache mapping guild IDs to rules text.

    Returns:
        None
    """
    while True:
        try:
            logger.debug("Refreshing server rules cache...")
            for guild in bot.guilds:
                try:
                    rules_text = await fetch_server_rules_from_channel(guild)
                    # Update shared cache
                    server_rules_cache[guild.id] = rules_text
                    # Persist to disk via bot_settings
                    try:
                        bot_settings.set_server_rules(guild.id, rules_text)
                    except Exception:
                        # If import or persist fails, continue; cache already updated
                        pass
                    if rules_text:
                        logger.debug(f"Cached rules for {guild.name} ({len(rules_text)} characters)")
                    else:
                        logger.warning(f"No rules found for {guild.name}")
                except Exception as e:
                    logger.warning(f"Failed to fetch rules for {guild.name}: {e}")
                    # Keep existing cache if fetch fails
                    if guild.id not in server_rules_cache:
                        server_rules_cache[guild.id] = ""
            logger.debug(f"Rules cache refreshed for {len(server_rules_cache)} guilds")
        except Exception as e:
            logger.error(f"Error during rules cache refresh: {e}")
        # Wait 5 minutes before next refresh (avoid hitting rate limits)
        await asyncio.sleep(300)


def get_server_rules(guild_id: int, server_rules_cache: dict) -> str:
    """
    Get cached server rules for a guild.

    Args:
        guild_id (int): The guild ID.
        server_rules_cache (dict): Cache mapping guild IDs to rules text.

    Returns:
        str: Cached rules text, or empty string if not found.
    """
    return server_rules_cache.get(guild_id, "")


async def delete_recent_messages(guild, member, seconds) -> int:
    """
    Deletes recent messages from a member in all text channels within the given time window.
    Returns the number of messages deleted.
    """
    if seconds <= 0:
        return 0

    window_start = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=seconds)
    deleted_count = 0

    for channel in _iter_moderatable_channels(guild):
        try:
            async for message in channel.history(limit=100, after=window_start):
                if message.author.id != member.id:
                    continue

                if await _safe_delete_message(message):
                    deleted_count += 1
        except discord.Forbidden:
            continue
        except Exception as exc:
            logger.error(f"Error deleting messages in {channel.name}: {exc}")

    return deleted_count


async def delete_messages_background(ctx: discord.ApplicationContext, user: discord.Member, delete_message_seconds: int):
    """
    Deletes messages in the background and sends a follow-up notification.
    This function runs asynchronously without blocking the main command response.
    
    Args:
        ctx (discord.ApplicationContext): The context of the command.
        user (discord.Member): The user whose messages to delete.
        delete_message_seconds (int): Number of seconds of messages to delete.
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
