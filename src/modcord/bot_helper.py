"""
Bot Helper Functions
===================

This module provides helper functions for the Discord Moderation Bot.
"""
import asyncio
import datetime
import discord
from .actions import ActionType
from .logger import get_logger

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
# Utility Functions
# ==========================================


def has_permissions(ctx: discord.ApplicationContext, **perms) -> bool:
    """
    Check if the command issuer has the required permissions.

    Args:
        ctx (discord.ApplicationContext): The context of the command.
        **perms: The permissions to check.

    Returns:
        bool: True if the user has permissions, False otherwise.
    """
    if not isinstance(ctx.author, discord.Member):
        return False
    return all(getattr(ctx.author.guild_permissions, perm, False) for perm in perms)


def parse_duration_to_seconds(duration_str: str) -> int:
    """
    Convert a human-readable duration string to its equivalent in seconds.

    Args:
        duration_str (str): The duration string to parse.

    Returns:
        int: The duration in seconds, or 0 if permanent or unrecognized.
    """
    return DURATIONS.get(duration_str, 0)


async def send_dm_to_user(user: discord.Member, message: str) -> bool:
    """
    Attempt to send a direct message to a user.

    Args:
        user (discord.Member): The user to DM.
        message (str): The message content.

    Returns:
        bool: True if DM sent successfully, False otherwise.
    """
    try:
        await user.send(message)
        return True
    except discord.Forbidden:
        # User may have DMs disabled or bot blocked.
        logger.info(f"Could not DM {user.display_name}: They may have DMs disabled.")
    except Exception as e:
        logger.error(f"Failed to send DM to {user.display_name}: {e}")
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
        ActionType.MUTE:    {"color": discord.Color.blue(),   "emoji": "🔇", "label": "Mute"},
        ActionType.TIMEOUT: {"color": discord.Color.blue(),   "emoji": "⏱️", "label": "Timeout"},
        ActionType.DELETE:  {"color": discord.Color.light_grey(), "emoji": "🗑️", "label": "Delete"},
        ActionType.NULL:    {"color": discord.Color.light_grey(), "emoji": "❓", "label": "No Action"},
    }
    
    # Unban is only used for scheduled unban notifications
    unban_details = {"color": discord.Color.green(), "emoji": "🔓", "label": "Unban"}

    details = action_details.get(action_type, unban_details if str(action_type) == "unban" else action_details[ActionType.NULL])
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
    dm_message = f"You have been {action_type.value} in {ctx.guild.name}.\n**Reason**: {reason}"
    await send_dm_to_user(user, dm_message)

    embed = await create_punishment_embed(
        action_type, user, reason, duration_str, ctx.user, ctx.bot.user
    )
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
    # Ignore if action is null, or message/guild/user is invalid.
    if action == ActionType.NULL or not message.guild or not isinstance(message.author, discord.Member):
        return

    user = message.author
    guild = message.guild
    channel = message.channel

    logger.info(f"AI action triggered: '{action.value}' on user {user.display_name} for reason: '{reason}'")

    try:
        if action == ActionType.DELETE:
            # Only delete the message, no further action.
            await message.delete()
            logger.info(f"Deleted message from {user.display_name}.")
            return

        # Prepare DM and embed for other actions.
        dm_message = ""
        embed = None

        if action == ActionType.BAN:
            dm_message = f"You have been banned from {guild.name}.\n**Reason**: {reason}"
            await send_dm_to_user(user, dm_message)
            await message.delete()
            await guild.ban(user, reason=f"AI Mod: {reason}")
            embed = await create_punishment_embed(ActionType.BAN, user, reason, PERMANENT_DURATION, bot_user, bot_user)

        elif action == ActionType.KICK:
            dm_message = f"You have been kicked from {guild.name}.\n**Reason**: {reason}"
            await send_dm_to_user(user, dm_message)
            await message.delete()
            await guild.kick(user, reason=f"AI Mod: {reason}")
            embed = await create_punishment_embed(ActionType.KICK, user, reason, issuer=bot_user, bot_user=bot_user)

        elif action in (ActionType.TIMEOUT, ActionType.MUTE):
            # Default timeout/mute duration is 10 minutes.
            duration_seconds = 10 * 60
            duration_str = "10 mins"
            until = discord.utils.utcnow() + datetime.timedelta(seconds=duration_seconds)
            dm_message = f"You have been timed out in {guild.name} for {duration_str}.\n**Reason**: {reason}"
            await user.timeout(until, reason=f"AI Mod: {reason}")
            await send_dm_to_user(user, dm_message)
            embed = await create_punishment_embed(ActionType.TIMEOUT, user, reason, duration_str, bot_user, bot_user)

        elif action == ActionType.WARN:
            dm_message = f"You have received a warning in {guild.name}.\n**Reason**: {reason}"
            await send_dm_to_user(user, dm_message)
            embed = await create_punishment_embed(ActionType.WARN, user, reason, issuer=bot_user, bot_user=bot_user)

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

async def unban_later(guild: discord.Guild, user_id: int, channel: discord.abc.Messageable, duration_seconds: int, bot):
    """
    Schedules a user to be unbanned after a specified duration.

    Args:
        guild (discord.Guild): The guild to unban from.
        user_id (int): The user's Discord ID.
        channel (discord.abc.Messageable): Channel to send unban notification.
        duration_seconds (int): How long to wait before unbanning.
        bot: The bot instance for fetching user.

    Returns:
        None
    """
    await asyncio.sleep(duration_seconds)
    try:
        user_obj = discord.Object(id=user_id)
        await guild.unban(user_obj, reason="Ban duration expired.")
        logger.info(f"Unbanned user {user_id} after ban expired.")

        # Attempt to send an embed notification to the channel.
        if isinstance(channel, (discord.TextChannel, discord.Thread)):
            try:
                user = await bot.fetch_user(user_id)
                embed = await create_punishment_embed(ActionType.UNBAN, user, "Ban duration expired.", issuer=bot.user, bot_user=bot.user)
                await channel.send(embed=embed)
            except Exception as e:
                logger.warning(f"Could not fetch user {user_id}, skipping embed: {e}")
    except discord.NotFound:
        logger.warning(f"Could not unban user {user_id}: User not found in ban list.")
    except Exception as e:
        logger.error(f"Failed to auto-unban user {user_id}: {e}")


# ==========================================
# Server Rules Management
# ==========================================

import re

async def fetch_server_rules_from_channel(guild: discord.Guild) -> str:
    """
    Fetches server rules from channels that contain rule-related keywords.

    Args:
        guild (discord.Guild): The guild to scan for rule channels.

    Returns:
        str: Combined rules text from all found channels.
    """
    rule_channel_pattern = re.compile(r"(guidelines|regulations|policy|policies|server[-_]?rules|rules)", re.IGNORECASE)

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
                logger.error(f"Error fetching rules from channel {channel.name} in {guild.name}: {e}")
    if messages:
        rules_text = "\n\n".join(messages)
        logger.info(f"Successfully fetched {len(messages)} rule messages from all rule channels")
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
            logger.info("Refreshing server rules cache...")
            for guild in bot.guilds:
                try:
                    rules_text = await fetch_server_rules_from_channel(guild)
                    server_rules_cache[guild.id] = rules_text
                    if rules_text:
                        logger.info(f"Cached rules for {guild.name} ({len(rules_text)} characters)")
                    else:
                        logger.warning(f"No rules found for {guild.name}")
                except Exception as e:
                    logger.error(f"Failed to fetch rules for {guild.name}: {e}")
                    # Keep existing cache if fetch fails
                    if guild.id not in server_rules_cache:
                        server_rules_cache[guild.id] = ""
            logger.info(f"Rules cache refreshed for {len(server_rules_cache)} guilds")
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
    now = datetime.datetime.now(datetime.timezone.utc)
    deleted_count = 0
    for channel in guild.text_channels:
        try:
            async for msg in channel.history(limit=100, after=now - datetime.timedelta(seconds=seconds)):
                if msg.author.id == member.id:
                    await msg.delete()
                    deleted_count += 1
        except Exception:
            continue
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
