"""
Moderation service for the bot.
"""

import asyncio
import datetime
import re
import discord

from ..config.logger import get_logger
from ..models.action import ActionType
from ..utils.embeds import create_punishment_embed
from ..utils.helpers import send_dm_to_user
from ..utils.constants import PERMANENT_DURATION

logger = get_logger(__name__)

class ModerationService:
    """
    Service for handling moderation actions.
    """
    def __init__(self, bot):
        self.bot = bot

    async def handle_error(self, ctx: discord.ApplicationContext, error: Exception):
        """
        Handle common errors in moderation commands.
        """
        if isinstance(error, discord.Forbidden):
            await ctx.followup.send("I do not have permissions to perform this action.", ephemeral=True)
        elif isinstance(error, AttributeError):
            await ctx.followup.send("Failed: Target is not a valid server member.", ephemeral=True)
        else:
            logger.error(f"An unexpected error occurred: {error}", exc_info=True)
            await ctx.followup.send("An unexpected error occurred.", ephemeral=True)

    async def send_dm_and_embed(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Member,
        action_type: ActionType,
        reason: str,
        duration_str: str | None = None
    ):
        """
        Send a DM to the user and an embed to the channel.
        """
        dm_message = f"You have been {action_type.value} in {ctx.guild.name}.\n**Reason**: {reason}"
        await send_dm_to_user(user, dm_message)

        embed = await create_punishment_embed(
            action_type, user, reason, duration_str, ctx.user, self.bot.user
        )
        await ctx.followup.send(embed=embed)

    async def take_action(self, action: ActionType, reason: str, message: discord.Message):
        """
        Applies a disciplinary action to the author of a message based on AI output.
        """
        if action == ActionType.NULL or not message.guild or not isinstance(message.author, discord.Member):
            return

        user = message.author
        guild = message.guild
        channel = message.channel

        logger.info(f"AI action triggered: '{action.value}' on user {user.display_name} for reason: '{reason}'")

        try:
            if action == ActionType.DELETE:
                await message.delete()
                logger.info(f"Deleted message from {user.display_name}.")
                return

            dm_message = ""
            embed = None

            if action == ActionType.BAN:
                dm_message = f"You have been banned from {guild.name}.\n**Reason**: {reason}"
                await send_dm_to_user(user, dm_message)
                await message.delete()
                await guild.ban(user, reason=f"AI Mod: {reason}")
                embed = await create_punishment_embed(ActionType.BAN, user, reason, PERMANENT_DURATION, self.bot.user, self.bot.user)

            elif action == ActionType.KICK:
                dm_message = f"You have been kicked from {guild.name}.\n**Reason**: {reason}"
                await send_dm_to_user(user, dm_message)
                await message.delete()
                await guild.kick(user, reason=f"AI Mod: {reason}")
                embed = await create_punishment_embed(ActionType.KICK, user, reason, issuer=self.bot.user, bot_user=self.bot.user)

            elif action in (ActionType.TIMEOUT, ActionType.MUTE):
                duration_seconds = 10 * 60
                duration_str = "10 mins"
                until = discord.utils.utcnow() + datetime.timedelta(seconds=duration_seconds)
                dm_message = f"You have been timed out in {guild.name} for {duration_str}.\n**Reason**: {reason}"
                await user.timeout(until, reason=f"AI Mod: {reason}")
                await send_dm_to_user(user, dm_message)
                embed = await create_punishment_embed(ActionType.TIMEOUT, user, reason, duration_str, self.bot.user, self.bot.user)

            elif action == ActionType.WARN:
                dm_message = f"You have received a warning in {guild.name}.\n**Reason**: {reason}"
                await send_dm_to_user(user, dm_message)
                embed = await create_punishment_embed(ActionType.WARN, user, reason, issuer=self.bot.user, bot_user=self.bot.user)

            if embed and isinstance(channel, (discord.TextChannel, discord.Thread)):
                await channel.send(embed=embed)

        except discord.Forbidden:
            logger.warning(f"Failed to execute '{action.value}' on {user.display_name}: Missing permissions.")
        except Exception as e:
            logger.error(f"Error executing action '{action.value}' on {user.display_name}: {e}", exc_info=True)

    async def unban_later(self, guild: discord.Guild, user_id: int, channel: discord.abc.Messageable, duration_seconds: int):
        """
        Schedules a user to be unbanned after a specified duration.
        """
        await asyncio.sleep(duration_seconds)
        try:
            user_obj = discord.Object(id=user_id)
            await guild.unban(user_obj, reason="Ban duration expired.")
            logger.info(f"Unbanned user {user_id} after ban expired.")

            if isinstance(channel, (discord.TextChannel, discord.Thread)):
                try:
                    user = await self.bot.fetch_user(user_id)
                    embed = await create_punishment_embed(ActionType.UNBAN, user, "Ban duration expired.", issuer=self.bot.user, bot_user=self.bot.user)
                    await channel.send(embed=embed)
                except Exception as e:
                    logger.warning(f"Could not fetch user {user_id}, skipping embed: {e}")
        except discord.NotFound:
            logger.warning(f"Could not unban user {user_id}: User not found in ban list.")
        except Exception as e:
            logger.error(f"Failed to auto-unban user {user_id}: {e}")

    async def fetch_server_rules_from_channel(self, guild: discord.Guild) -> str:
        """
        Fetches server rules from channels that contain rule-related keywords.
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

    async def delete_recent_messages(self, guild, member, seconds) -> int:
        """
        Deletes recent messages from a member in all text channels.
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

    async def delete_messages_background(self, ctx: discord.ApplicationContext, user: discord.Member, delete_message_seconds: int):
        """
        Deletes messages in the background and sends a follow-up notification.
        """
        try:
            deleted = await self.delete_recent_messages(ctx.guild, user, delete_message_seconds)
            if deleted:
                await ctx.followup.send(f"🗑️ Deleted {deleted} recent messages from {user.mention}.", ephemeral=True)
            else:
                await ctx.followup.send(f"No recent messages found to delete from {user.mention}.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error deleting messages in background: {e}")
            await ctx.followup.send("⚠️ Action completed, but failed to delete some messages.", ephemeral=True)
