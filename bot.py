import asyncio
import collections
import datetime
import logging
import os
import discord
import yaml
from dotenv import load_dotenv
import ai_model as ai
from discord import Option

# ==========================================
# Logging and Configuration Setup
# ==========================================
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Ensure working directory is the location of this file for file operations
os.chdir(os.path.dirname(os.path.abspath(__file__)))

load_dotenv()  # Load environment variables from .env file

token = os.getenv('Mod_Bot_Token')

# Load server rules from config.yml
try:
    with open("config.yml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    SERVER_RULES = config["server_rules"]
except FileNotFoundError:
    logger.error("[CONFIG] Failed to load config from config.yml: File not found.")
    SERVER_RULES = []
except Exception as e:
    logger.error(f"[CONFIG] Failed to load config from config.yml: {e}")
    SERVER_RULES = []

# ==========================================
# Discord Bot Initialization & State
# ==========================================
bot = discord.Bot(intents=discord.Intents.all())  # Create bot with all intents enabled

user_last_processed = {}  # Tracks last processed message per user (avoid duplicates)

# Chat history per channel, max 50 messages per channel for context
db_history = collections.defaultdict(lambda: collections.deque(maxlen=50))

# ==========================================
# Moderation Action Handler
# ==========================================
async def take_action(action: str, reason: str, message: discord.Message):
    """
    Applies a disciplinary action to the author of a given Discord message.

    Parameters:
        action (str): Action to take ("ban", "kick", "timeout", "warn", "delete", or "null")
        reason (str): Reason for the action
        message (discord.Message): The Discord message triggering the action
    """
    if action == "null":
        return  # No action needed

    user = message.author
    channel = message.channel
    guild = message.guild

    # Only apply actions if user is a guild member and in a guild
    if guild and isinstance(user, discord.Member):
        try:
            if action == "delete":
                await message.delete()
                logger.info(f"Deleted message from {user} for reason: {reason}")
                return

            embed = None

            if action == "ban":
                # Ban user permanently (or until explicitly unbanned)
                try:
                    await user.send(f"You have been banned from {guild.name}.\nReason: {reason}")
                except Exception as e:
                    logger.warning(f"Could not DM user for ban: {e}")

                await guild.ban(user, reason=reason)
                embed = await create_punishment_embed(
                    action_type="Ban",
                    user=user,
                    reason=reason,
                    duration="Till the end of time",
                    issuer=bot.user
                )
                logger.info(f"Banned {user} for reason: {reason}")

            elif action == "kick":
                # Kick user from the guild
                try:
                    await user.send(f"You have been kicked from {guild.name}.\nReason: {reason}")
                except Exception as e:
                    logger.warning(f"Could not DM user for kick: {e}")

                await guild.kick(user, reason=reason)
                embed = await create_punishment_embed(
                    action_type="Kick",
                    user=user,
                    reason=reason,
                    issuer=bot.user
                )
                logger.info(f"Kicked {user} for reason: {reason}")

            elif action == "timeout" or action == "mute":
                # Timeout user for 10 minutes
                duration_seconds = 10 * 60  # 10 minutes
                until = discord.utils.utcnow() + datetime.timedelta(seconds=duration_seconds)
                try:
                    await user.timeout(until, reason=reason)
                    try:
                        await user.send(
                            f"You have been timed out in {guild.name} for {duration_seconds / 60:.2f} minutes.\nReason: {reason}"
                        )
                    except Exception as e:
                        logger.warning(f"Could not DM user for timeout: {e}")
                    embed = await create_punishment_embed(
                        action_type="Timeout",
                        user=user,
                        reason=reason,
                        duration="10 mins",
                        issuer=bot.user
                    )
                    logger.info(f"Timed out {user} for reason: {reason}")
                except discord.errors.Forbidden:
                    logger.warning(f"Failed to timeout {user}: Missing permissions")

            elif action == "warn":
                # Send warning to user
                try:
                    await user.send(
                        f"You have received a warning in {guild.name}.\nReason: {reason}"
                    )
                except Exception as e:
                    logger.warning(f"Could not DM user for warning: {e}")

                embed = await create_punishment_embed(
                    action_type="Warn",
                    user=user,
                    reason=reason,
                    issuer=bot.user
                )
                logger.info(f"Warned {user} for reason: {reason}")

            # Send embed notification to the channel
            if embed and isinstance(channel, (discord.TextChannel, discord.Thread)):
                await channel.send(embed=embed)

        except Exception as e:
            logger.error(f"Error executing action '{action}': {e}")
    else:
        logger.warning(f"Cannot apply action '{action}' to message: Not in a guild or author is not a Member")


# ==========================================
# Scheduled Unban Helper
# ==========================================
async def unban_later(guild, user_id, channel, duration_seconds):
    """
    Unbans a user after the specified duration.

    Parameters:
        guild (discord.Guild): The Discord guild
        user_id (int): The user ID to unban
        channel (discord.TextChannel | discord.Thread): Channel to send notification
        duration_seconds (int): Ban duration in seconds
    """
    await asyncio.sleep(duration_seconds)
    try:
        user_obj = discord.Object(id=user_id)
        await guild.unban(user_obj, reason="Ban expired")

        if isinstance(channel, (discord.TextChannel, discord.Thread)):
            user = bot.get_user(user_id)
            if user:
                embed = await create_punishment_embed(
                    action_type="Unban",
                    user=user,
                    reason="Ban duration expired",
                    issuer=bot.user
                )
                await channel.send(embed=embed)
            else:
                embed = discord.Embed(
                    title="🔓 User Unbanned",
                    description=f"<@{user_id}> has been unbanned (ban expired).",
                    color=discord.Color.green()
                )
                await channel.send(embed=embed)

        user = bot.get_user(user_id)
        if user:
            await user.send(
                f"🔓 You have been unbanned from {guild.name}. Your ban has expired."
            )
        else:
            logger.warning(f"User {user_id} not found in cache. Could not send unban notification.")
    except Exception as e:
        logger.error(f"Failed to unban user {user_id}: {e}")


# ==========================================
# Embed Builder for Punishment Actions
# ==========================================
async def create_punishment_embed(action_type, user, reason, duration=None, issuer=None):
    """
    Creates a standardized embed for punishment actions.

    Parameters:
        action_type (str): "Ban", "Kick", "Warn", etc.
        user (discord.User | discord.Member): The punished user
        reason (str): Reason for punishment
        duration (str | int, optional): Duration string or seconds
        issuer (discord.User | discord.Member, optional): The staff member who issued the punishment

    Returns:
        discord.Embed: The constructed embed object
    """
    # Set color based on severity
    colors = {
        "Ban": discord.Color.red(),
        "Kick": discord.Color.orange(),
        "Warn": discord.Color.yellow(),
        "Mute": discord.Color.blue(),
        "Timeout": discord.Color.blue()
    }
    color = colors.get(action_type, discord.Color.light_gray())

    # Set emoji based on action type
    emojis = {
        "Ban": "🔨",
        "Kick": "👢",
        "Warn": "⚠️",
        "Mute": "🔇",
        "Timeout": "⏱️",
        "Unban": "🔓"
    }
    emoji = emojis.get(action_type, "❓")

    # Create the embed
    embed = discord.Embed(
        title=f"{emoji} {action_type} Issued",
        description=f"A punishment has been issued on the server.",
        color=color,
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )

    # Add embed fields
    embed.add_field(name="**Type**", value=action_type, inline=True)
    embed.add_field(name="**Issued to**", value=f"{user.mention} ({user.name})", inline=True)

    if issuer:
        embed.add_field(name="**Issued by**", value=issuer.mention, inline=True)

    embed.add_field(name="**Reason**", value=reason, inline=False)

    # Add duration and expiry info if provided
    if duration and duration != "Till the end of time":
        # Calculate expiry for temporary punishments
        if isinstance(duration, int) or (isinstance(duration, str) and duration.isdigit()):
            duration_seconds = int(duration)
            expire_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=duration_seconds)
            unix_timestamp = int(expire_time.timestamp())
            embed.add_field(
                name="**Duration**",
                value=f"{duration}\nExpires: <t:{unix_timestamp}:F> (<t:{unix_timestamp}:R>)",
                inline=False
            )
        else:
            embed.add_field(name="**Duration**", value=duration, inline=False)
    elif duration == "Till the end of time":
        embed.add_field(name="**Duration**", value="Till the end of time", inline=False)

    return embed

# ==========================================
# Slash Commands
# ==========================================
@bot.slash_command(name="test", description="Checks to see if I am online")
async def test(ctx):
    """
    Test command for bot health and latency.
    """
    await ctx.respond(f":white_check_mark: I am working! \nLatency: {(bot.latency * 1000):.2f} ms.")


# ==================================================
# Kick Command (Admin Only, No Duration)
# ==================================================
@bot.slash_command(name="kick", description="Kick a user (Admin only)")
async def kick(ctx: discord.Interaction, user: discord.Member, reason: str = "Kicked by an admin/moderator"):
    """
    Kicks a user from the server.

    Only available to members with kick permissions.
    """
    if not isinstance(ctx.user, discord.Member) or not ctx.user.guild_permissions.kick_members:
        await ctx.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    if user.id == ctx.user.id:
        await ctx.response.send_message("You cannot kick yourself.", ephemeral=True)
        return

    if user.guild_permissions.administrator:
        await ctx.response.send_message("You cannot kick an administrator.", ephemeral=True)
        return

    guild_name = ctx.guild.name if ctx.guild is not None else "this server"
    try:
        await user.send(f"You have been kicked from {guild_name}.\nReason: {reason}")
    except Exception as e:
        logger.warning(f"Could not DM user for kick: {e}")

    await ctx.response.send_message(f"Kicking {user.mention}", ephemeral=True)
    await user.kick(reason=reason)

    channel = ctx.channel
    if isinstance(channel, (discord.TextChannel, discord.Thread)):
        embed = await create_punishment_embed(
            action_type="Kick",
            user=user,
            reason=reason,
            issuer=ctx.user
        )
        await channel.send(embed=embed)
    else:
        logger.warning("Cannot send message: ctx.channel is not a TextChannel or Thread.")
    return


# ==========================================
# Ban Command with Duration Options
# ==========================================
# Note: This command allows banning a user for a specific duration or permanently.
@bot.slash_command(name="ban", description="Ban a user for a specific period (Admin only)")
async def ban(
    ctx: discord.Interaction,
    user: discord.Member,
    reason = Option(str, "Reason for ban", default="Banned by an admin/moderator"),
    duration = Option(str, "Ban duration", choices=[
        "60 secs", "5 mins", "10 mins", "1 hour", "1 day", "1 week", "Till the end of time"], default="Till the end of time")
):
    """
    Bans a user for a configurable period.

    Only available to members with ban permissions.
    """
    def parse_duration(duration_str):
        mapping = {
            "60 secs": 60,
            "5 mins": 5 * 60,
            "10 mins": 10 * 60,
            "1 hour": 60 * 60,
            "1 day": 24 * 60 * 60,
            "1 week": 7 * 24 * 60 * 60,
            "Till the end of time": 0
        }
        return mapping.get(duration_str, 0)

    duration_seconds = parse_duration(duration)

    if not isinstance(ctx.user, discord.Member) or not ctx.user.guild_permissions.ban_members:
        await ctx.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    if user.id == ctx.user.id:
        await ctx.response.send_message("You cannot ban yourself.", ephemeral=True)
        return

    if user.guild_permissions.administrator:
        await ctx.response.send_message("You cannot ban an administrator.", ephemeral=True)
        return

    guild_name = ctx.guild.name if ctx.guild is not None else "this server"
    expire_text = ""
    if duration_seconds > 0:
        expire_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=duration_seconds)
        unix_timestamp = int(expire_time.timestamp())
        expire_text = f"\nBan expires at: <t:{unix_timestamp}:F>"

    try:
        await user.send(f"You have been banned from {guild_name}.\nReason: {reason}{expire_text}")
    except Exception as e:
        logger.warning(f"Could not DM user for ban: {e}")

    await ctx.response.send_message(f"Banning {user.mention}", ephemeral=True)
    await user.ban(reason=str(reason))

    channel = ctx.channel
    if isinstance(channel, (discord.TextChannel, discord.Thread)):
        embed = await create_punishment_embed(
            action_type="Ban",
            user=user,
            reason=reason,
            duration=duration,
            issuer=ctx.user
        )
        await channel.send(embed=embed)
    else:
        logger.warning("Cannot send message: ctx.channel is not a TextChannel or Thread.")

    if duration_seconds > 0 and ctx.guild is not None:
        asyncio.create_task(unban_later(ctx.guild, user.id, ctx.channel, duration_seconds))

    return

# ==========================================
# Event Handlers
# ==========================================
@bot.event
async def on_ready():
    """
    Fired when the bot is fully ready and connected.
    """
    print(f"Bot connected as {bot.user} at {datetime.datetime.now()}")

    # If reloading was triggered, send a message to the channel
    if os.path.exists("reload_success.flag"):
        try:
            with open("reload_success.flag", "r") as f:
                channel_id = int(f.read().strip())
            channel = bot.get_channel(channel_id)
            if isinstance(channel, (discord.TextChannel, discord.Thread)):
                await channel.send(":wireless: Bot reloaded successfully!")
        except Exception as e:
            logger.error(f"Failed to send reload success message: {e}")
        finally:
            os.remove("reload_success.flag")
            print("=============================================================")


# ==========================================
# Message Handler for AI Moderation
# ==========================================
# Note: This is the main moderation logic that uses the AI model to determine actions
@bot.event
async def on_message(message):
    """
    Handles message-based moderation using the AI model.

    - Ignores messages from the bot itself and server administrators.
    - Maintains per-channel message history.
    - Uses AI model to determine appropriate moderation action.
    - Applies the action if necessary.
    """
    if message.author == bot.user:
        return
    elif isinstance(message.author, discord.Member) and message.author.guild_permissions.administrator:
        return

    raw_content = message.content
    username = str(message.author)
    hist = db_history[message.channel.id]
    role = "assistant" if message.author == bot.user else "user"
    hist.append({"role": role, "content": raw_content, "username": username})

    action_response = await ai.get_appropriate_action(
        current_message=raw_content,
        history=list(hist),
        username=username
    )

    if ":" in action_response:
        action, reason = action_response.split(":", 1)
        action = action.strip().lower()
        reason = reason.strip()
    else:
        action, reason = "null", "AI model error"

    await take_action(action, reason, message)

# ==========================================
# Main Entrypoint
# ==========================================
def main():
    """
    Main entry point for the bot. Verifies token, then starts bot.
    """
    if not token:
        logger.error("Mod_Bot_Token environment variable not set")
        return
    bot.run(token)

if __name__ == "__main__":
    main()