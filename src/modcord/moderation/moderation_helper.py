"""
Moderation helper functions for applying actions and sending notifications.

This module provides utility functions for:
- Finding users in server moderation batches
- Sending moderation notifications using ActionData
- Applying moderation actions from ActionData objects
"""

import datetime
import discord

from modcord.cog.listener.scheduler_cog import UnbanSchedulerCog
from modcord.datatypes.action_datatypes import ActionData, ActionType
from modcord.datatypes.discord_datatypes import UserID
from modcord.datatypes.moderation_datatypes import ServerModerationBatch, ModerationUser
from modcord.ui import action_embed_ui
from modcord.util.discord import discord_utils
from modcord.util.logger import get_logger

logger = get_logger("moderation_helper")


# ---------------------------------------------------------------------------
# Utility functions (stateless)
# ---------------------------------------------------------------------------

def find_target_user_in_batch(
        batch: ServerModerationBatch,
        user_id: UserID
) -> ModerationUser | None:
    """
    Find a target user in a server batch by user ID.
    
    Args:
        batch: ServerModerationBatch to search.
        user_id: UserID to find.
    
    Returns:
        ModerationUser if found with valid Discord context, None otherwise.
    """
    target_user = next((u for u in batch.users if u.user_id == user_id), None)

    if not target_user or not target_user.channels:
        logger.warning(
            "[MODERATION HELPER] Target user %s not found in batch or has no channels",
            user_id
        )
        return None

    if not target_user.discord_member or not target_user.discord_guild:
        logger.warning(
            "[MODERATION HELPER] Target user %s missing Discord context",
            user_id
        )
        return None

    return target_user


def compute_action_duration(action: ActionData) -> datetime.timedelta:
    """
    Compute the duration timedelta from an ActionData object.

    All durations (timeout_duration, ban_duration) are stored and interpreted
    in SECONDS only — never minutes or hours.

    Args:
        action: ActionData containing timeout_duration or ban_duration (in seconds)

    Returns:
        timedelta if action has a duration, None otherwise
    """
    DISCORD_MAX_TIMEOUT_SECONDS = 28 * 24 * 60 * 60  # 28 days

    match action.action:
        case ActionType.TIMEOUT:
            return datetime.timedelta(seconds=min(action.timeout_duration, DISCORD_MAX_TIMEOUT_SECONDS))

        case ActionType.BAN:
            return datetime.timedelta(action.ban_duration)

        case _:
            return datetime.timedelta(seconds=0)



async def send_action_notification(
        action: ActionData,
        user: discord.Member,
        guild: discord.Guild,
        channel: discord.TextChannel,
        bot_user: discord.User | discord.ClientUser,
) -> None:
    """
    Send moderation notification embed to the user via DM and to channel.
    
    This is the single notification function that extracts all needed info
    from ActionData - the canonical representation throughout the pipeline.
    
    Args:
        action: ActionData containing action type, reason, and duration info
        user: Target user
        guild: Guild context
        channel: Channel to post embed in
        bot_user: Bot user for footer attribution
    """
    duration = compute_action_duration(action)

    embed = await action_embed_ui.create_action_embed(
        action=action,
        user=user,
        guild=guild,
        admin=bot_user,
        duration=duration,
    )

    # Try to send DM
    try:
        await user.send(embed=embed)
    except discord.Forbidden:
        logger.debug(f"Cannot send DM to user {user.id}: DMs disabled")
    except Exception as e:
        logger.error(f"Error sending DM to {user.id}: {e}")

    # Post to channel if it exists
    if channel:
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            logger.warning(f"Cannot post to channel {channel.id}: missing permissions")
        except Exception as e:
            logger.error(f"Error posting to channel {channel.id}: {e}")


async def apply_action(
        action: ActionData,
        member: discord.Member,
        bot: discord.Bot,
        notification_channel: discord.TextChannel | None = None,
) -> bool:
    """
    Apply a moderation action to a user using the ActionData object.
    
    This is the single entry point for executing moderation actions. It:
    1. Deletes messages if specified in ActionData
    2. Applies the moderation action (timeout, kick, ban, etc.)
    3. Sends notifications via DM and channel
    4. Logs the action to the database
    5. Schedules follow-up tasks (e.g., unban for temp bans)
    
    Args:
        action: ActionData containing all action parameters
        member: Discord member to apply action to
        bot: Bot instance for API calls
        notification_channel: Channel to post notification embed to (derived from batch)
    
    Returns:
        bool: True if action was successfully applied
    """
    # Validate required objects
    if bot is None or bot.user is None:
        logger.error("Bot client is None or bot user is None, cannot apply moderation action")
        return False

    guild = bot.get_guild(int(action.guild_id))

    if guild is None:
        logger.error("Guild is None or missing, cannot apply moderation action")
        return False

    channel = notification_channel

    # now do actual stuff — delete messages per channel
    for spec in action.channel_deletions:
        del_channel = guild.get_channel(int(spec.channel_id))
        if del_channel is None or not isinstance(del_channel, discord.TextChannel | discord.Thread):
            logger.warning(
                "Channel %s not found or not a text channel/thread in guild %s",
                spec.channel_id,
                guild.id,
            )
            continue
        await discord_utils.delete_messages_from_channel(del_channel, spec.message_ids)

    try:
        match action.action:
            case ActionType.WARN:
                if channel:
                    await send_action_notification(action, member, guild, channel, bot.user)
                return True

            case ActionType.DELETE:
                # Messages already deleted above
                return True

            case ActionType.TIMEOUT:
                duration = compute_action_duration(action)
                if duration is None:
                    duration = datetime.timedelta(seconds=0)  # Default to no timeout
                until = discord.utils.utcnow() + duration

                await member.timeout(until, reason=f"ModCord: {action.reason}")
                if channel:
                    await send_action_notification(action, member, guild, channel, bot.user)
                return True

            case ActionType.KICK:
                await guild.kick(member, reason=f"ModCord: {action.reason}")
                if channel:
                    await send_action_notification(action, member, guild, channel, bot.user)
                return True

            case ActionType.BAN:
                duration = compute_action_duration(action)

                await guild.ban(member, reason=f"ModCord: {action.reason}")

                try:
                    unban_cog = bot.cogs.get("UnbanSchedulerCog")
                    if isinstance(unban_cog, UnbanSchedulerCog):
                        await unban_cog.schedule(
                            guild=guild,
                            user_id=action.user_id,
                            duration_seconds=int(duration.total_seconds()),
                            reason="Ban duration expired.",
                        )
                    else:
                        logger.error("UnbanSchedulerCog not loaded, cannot schedule unban")
                except Exception as e:
                    logger.error(f"Failed to schedule unban for user {member.id}: {e}")

                if channel:
                    await send_action_notification(action, member, guild, channel, bot.user)
                return True

            case _:
                logger.warning(f"Unknown action type: {action.action}")
                return False

    except discord.Forbidden:
        logger.warning(f"Permission denied applying {action.action.value} to {member.id} in {guild.id}")
        return False
    except Exception as e:
        logger.error(f"Error applying {action.action.value}: {e}", exc_info=True)
        return False
