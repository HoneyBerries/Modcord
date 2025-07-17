"""
Discord Moderation Bot
======================

A Discord bot that uses an AI model to moderate chat, handle rule violations,
and provide server administration commands for manual moderation actions like
banning, kicking, and timing out users.

Features:
- Automated message moderation using a custom AI model.
- Slash commands for manual moderation (`/timeout`, `/kick`, `/ban`).
- Per-channel chat history context for the AI model.
- Standardized and informative punishment embeds.
- Temporary ban and timeout support with automatic unbanning/un-timing out.
- Configuration loaded from `config.yml` for server rules.
- Graceful reload notifications.
"""

import asyncio
import collections
import datetime
import logging
import os
from pathlib import Path
import discord
from discord import Option
from discord.ext import commands
from dotenv import load_dotenv
from discord.ext.commands.errors import MissingPermissions
from actions import ActionType
import ai_model as ai
import bot_helper

# ==========================================
# Configuration and Logging Setup
# ==========================================

# Use pathlib for robust path management, ensuring paths are relative to the script's location.
BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)  # Set working directory for compatibility with relative paths if needed.

# Configure logging for better debugging and monitoring.
logging.basicConfig(
    level=logging.INFO,  # Set to INFO for more detailed operational logs.
    format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Load environment variables from a .env file.
load_dotenv()
DISCORD_BOT_TOKEN = os.getenv('Mod_Bot_Token')

# Server rules cache - will be populated dynamically from Discord channels
SERVER_RULES_CACHE = {}  # guild_id -> rules_text

# ==========================================
# Bot Initialization & State
# ==========================================
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True

bot = discord.Bot(intents=intents)

# Per-channel chat history, using a defaultdict with a deque for efficient, capped storage.
# This provides conversational context for the AI model.
db_history = collections.defaultdict(lambda: collections.deque(maxlen=50))

# ==========================================
# Slash Commands
# ==========================================

@bot.slash_command(name="test", description="Checks if the bot is online and its latency.")
async def test(ctx: discord.ApplicationContext):
    """
    A simple health-check command to verify bot status and latency.

    Args:
        ctx (discord.ApplicationContext): The context of the command.

    Returns:
        None
    """
    latency_ms = bot.latency * 1000
    await ctx.respond(f":white_check_mark: I am online and working!\n**Latency**: {latency_ms:.2f} ms.", ephemeral=True)


# ===========================================
# Command Groups
# ===========================================
mod_group = bot.create_group("mod", "Moderation commands")
debug_group = bot.create_group("debug", "Debugging commands")

# ==========================================
# Moderation Command Error Handler
# ==========================================

@mod_group.error
async def mod_group_error_handler(ctx, error):
    """
    Handles errors for moderation commands, providing user-friendly feedback.

    Args:
        ctx (discord.ApplicationContext): The context of the command.
        error (Exception): The error raised.

    Returns:
        None
    """
    if isinstance(error, MissingPermissions):
        await ctx.respond(
            "❌ You do not have the required permissions to use this command.", ephemeral=True
        )
    else:
        logger.error(f"Error in moderation command: {type(error).__name__}: {error}", exc_info=True)
        await ctx.respond(
            "❌ An unexpected error occurred while processing your moderation command.", ephemeral=True
        )


# ==========================================
# Moderation Commands
# ==========================================

@mod_group.command(name="warn", description="Warn a user for a specified reason.")
@commands.has_permissions(manage_messages=True)
async def warn(
    ctx: discord.ApplicationContext,
    user: Option(discord.Member, "The user to warn.", required=True),  # type: ignore
    reason: Option(str, "Reason for the warning.", default="Breaking server rules")  # type: ignore
) -> None:
    """
    Issues a warning to a user and sends a DM notification.

    Args:
        ctx (discord.ApplicationContext): The context of the command.
        user (discord.Member): The user to warn.
        reason (str): Reason for the warning.

    Returns:
        None
    """
    await ctx.defer()  # Immediately acknowledge the interaction

    try:
        dm_message: str = f"You have been warned in {ctx.guild.name}.\n**Reason**: {reason}"
        await bot_helper.send_dm_to_user(user, dm_message)

        embed: discord.Embed = await bot_helper.create_punishment_embed(
            ActionType.WARN, user, reason, issuer=ctx.user, bot_user=bot.user
        )
        await ctx.followup.send(embed=embed)
    except discord.Forbidden:
        await ctx.followup.send("I do not have permissions to warn this user.", ephemeral=True)
    except Exception as e:
        logger.error(f"Failed to warn {user.display_name}: {e}")
        await ctx.followup.send("An unexpected error occurred.", ephemeral=True)

@mod_group.command(name="timeout", description="Timeout a user for a specified duration.")
@commands.has_permissions(moderate_members=True)
async def timeout(
    ctx: discord.ApplicationContext,
    user: Option(discord.Member, "The user to timeout.", required=True),  # type: ignore
    duration: Option(str, "Duration of the timeout.", choices=[
        "60 secs", "5 mins", "10 mins", "30 mins", "1 hour", "2 hours", "1 day"], default="10 mins"), # type: ignore
    reason: Option(str, "Reason for the timeout.", default="No reason provided.")  # type: ignore
) -> None:
    """
    Applies a timeout to a user for a specified duration.

    Args:
        ctx (discord.ApplicationContext): The context of the command.
        user (discord.Member): The user to timeout.
        duration (str): Duration of the timeout.
        reason (str): Reason for the timeout.

    Returns:
        None
    """
    await ctx.defer()
    try:
        if not isinstance(user, discord.Member):
            return await ctx.followup.send("This user is not a member of the server.", ephemeral=True)
        if user.id == ctx.user.id:
            return await ctx.followup.send("You cannot timeout yourself.", ephemeral=True)
        if user.guild_permissions.administrator:
            return await ctx.followup.send("You cannot timeout an administrator.", ephemeral=True)

        duration_seconds: int = bot_helper.parse_duration_to_seconds(duration)
        until: datetime.datetime = discord.utils.utcnow() + datetime.timedelta(seconds=duration_seconds)

        await user.timeout(until, reason=reason)
        dm_message: str = f"You have been timed out in {ctx.guild.name} for {duration}.\n**Reason**: {reason}"
        await bot_helper.send_dm_to_user(user, dm_message)
        embed: discord.Embed = await bot_helper.create_punishment_embed(
            ActionType.TIMEOUT, user, reason, duration, ctx.user, bot.user
        )
        await ctx.followup.send(embed=embed)
    except discord.Forbidden:
        await ctx.followup.send("I do not have permissions to timeout this user.", ephemeral=True)
    except AttributeError:
        await ctx.followup.send("Failed: Target is not a valid server member.", ephemeral=True)
    except Exception as e:
        logger.error(f"Failed to timeout {getattr(user, 'display_name', str(user))}: {e}")
        await ctx.followup.send("An unexpected error occurred.", ephemeral=True)

@mod_group.command(name="kick", description="Kick a user from the server.")
@commands.has_permissions(kick_members=True)
async def kick(
    ctx: discord.ApplicationContext,
    user: Option(discord.Member, "The user to kick.", required=True),  # type: ignore
    reason: Option(str, "Reason for the kick.", default="No reason provided.")  # type: ignore
) -> None:
    """
    Kicks a user from the server and sends a DM notification.

    Args:
        ctx (discord.ApplicationContext): The context of the command.
        user (discord.Member): The user to kick.
        reason (str): Reason for the kick.

    Returns:
        None
    """
    await ctx.defer()
    
    try:
        if not isinstance(user, discord.Member):
            return await ctx.followup.send("This user is not a member of the server.", ephemeral=True)
        if user.id == ctx.user.id:
            return await ctx.followup.send("You cannot kick yourself.", ephemeral=True)
        if user.guild_permissions.administrator:
            return await ctx.followup.send("You cannot kick an administrator.", ephemeral=True)

        dm_message: str = f"You have been kicked from {ctx.guild.name}.\n**Reason**: {reason}"
        await bot_helper.send_dm_to_user(user, dm_message)
        await user.kick(reason=reason)
        embed: discord.Embed = await bot_helper.create_punishment_embed(
            ActionType.KICK, user, reason, issuer=ctx.user, bot_user=bot.user
        )
        await ctx.followup.send(embed=embed)
    except discord.Forbidden:
        await ctx.followup.send("I do not have permissions to kick this user.", ephemeral=True)
    except AttributeError:
        await ctx.followup.send("Failed: Target is not a valid server member.", ephemeral=True)
    except Exception as e:
        logger.error(f"Failed to kick {getattr(user, 'display_name', str(user))}: {e}")
        await ctx.followup.send("An unexpected error occurred.", ephemeral=True)

@mod_group.command(name="ban", description="Ban a user from the server.")
@commands.has_permissions(ban_members=True)
async def ban(
    ctx: discord.ApplicationContext,
    user: Option(discord.Member, "The user to ban.", required=True),  # type: ignore
    duration: Option(str, "Duration of the ban.", choices=[
        "60 secs", "5 mins", "10 mins", "1 hour", "1 day", "1 week", "Till the end of time"], default="Till the end of time"), # type: ignore
    reason: Option(str, "Reason for the ban.", default="No reason provided."),  # type: ignore
    delete_message_days: Option(int, "Number of days of messages to delete (0-7).", choices=[0, 1, 7], default=1)  # type: ignore
) -> None:
    """
    Bans a user from the server, optionally for a temporary duration.

    Args:
        ctx (discord.ApplicationContext): The context of the command.
        user (discord.Member): The user to ban.
        duration (str): Duration of the ban.
        reason (str): Reason for the ban.
        delete_message_days (int): Number of days of messages to delete.

    Returns:
        None
    """
    await ctx.defer()
    
    try:
        if not isinstance(user, discord.Member):
            return await ctx.followup.send("This user is not a member of the server.", ephemeral=True)
        if user.id == ctx.user.id:
            return await ctx.followup.send("You cannot ban yourself.", ephemeral=True)
        if user.guild_permissions.administrator:
            return await ctx.followup.send("You cannot ban an administrator.", ephemeral=True)

        duration_seconds: int = bot_helper.parse_duration_to_seconds(duration)
        dm_message: str = f"You have been banned from {ctx.guild.name} for: {duration}.\n**Reason**: {reason}"
        await bot_helper.send_dm_to_user(user, dm_message)
        await ctx.guild.ban(user, reason=reason, delete_message_days=delete_message_days)
        embed: discord.Embed = await bot_helper.create_punishment_embed(
            ActionType.BAN, user, reason, duration, ctx.user, bot.user
        )
        await ctx.followup.send(embed=embed)

        if duration_seconds > 0:
            logger.info(f"Scheduling unban for {getattr(user, 'display_name', str(user))} in {duration_seconds} seconds.")
            asyncio.create_task(bot_helper.unban_later(ctx.guild, user.id, ctx.channel, duration_seconds, bot))
    except discord.Forbidden:
        await ctx.followup.send("I do not have permissions to ban this user.", ephemeral=True)
    except AttributeError:
        await ctx.followup.send("Failed: Target is not a valid server member.", ephemeral=True)
    except Exception as e:
        logger.error(f"Failed to ban {getattr(user, 'display_name', str(user))}: {e}")
        await ctx.followup.send("An unexpected error occurred.", ephemeral=True)


# ==========================================
# Debugging Commands
# ==========================================

@debug_group.command(name="refresh_rules", description="Manually refresh the server rules cache.")
@commands.has_permissions(administrator=True)
async def refresh_rules_command(ctx: discord.ApplicationContext):
    """
    Manually refresh the server rules cache for this guild.

    Args:
        ctx (discord.ApplicationContext): The context of the command.

    Returns:
        None
    """
    await ctx.defer()
    
    try:
        rules_text = await bot_helper.fetch_server_rules_from_channel(ctx.guild)
        SERVER_RULES_CACHE[ctx.guild.id] = rules_text
        
        if rules_text:
            embed = discord.Embed(
                title="✅ Rules Cache Refreshed",
                description=f"Successfully updated rules cache with {len(rules_text)} characters from rules channel.",
                color=discord.Color.green(),
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            embed.add_field(name="Rules Preview", value=rules_text[:500] + ("..." if len(rules_text) > 500 else ""), inline=False)
        else:
            embed = discord.Embed(
                title="⚠️ No Rules Found",
                description="No rules channel found or no content in rules channel.",
                color=discord.Color.yellow(),
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
        
        await ctx.followup.send(embed=embed, ephemeral=True)
        
    except Exception as e:
        logger.error(f"Failed to refresh rules for {ctx.guild.name}: {e}")
        await ctx.followup.send("An error occurred while refreshing rules.", ephemeral=True)


@debug_group.command(name="show_rules", description="Display the current cached server rules.")
@commands.has_permissions(manage_messages=True)
async def show_rules(ctx: discord.ApplicationContext):
    """
    Display the current cached server rules.

    Args:
        ctx (discord.ApplicationContext): The context of the command.

    Returns:
        None
    """
    await ctx.defer()
    
    rules_text = bot_helper.get_server_rules(ctx.guild.id, SERVER_RULES_CACHE)
    
    if rules_text:
        embed = discord.Embed(
            title="📋 Server Rules",
            description=rules_text[:4000],  # Discord embed limit
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_footer(text=f"Rules for {ctx.guild.name}")
        await ctx.followup.send(embed=embed)
    else:
        embed = discord.Embed(
            title="❌ No Rules Available",
            description="No server rules are currently cached. Try `/mod refresh_rules` first.",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        await ctx.followup.send(embed=embed, ephemeral=True)


# ==========================================
# Event Handlers
# ==========================================

@bot.event
async def on_ready():
    """
    Fired when the bot successfully connects to Discord.
    Sets presence, starts background tasks, and logs connection.

    Returns:
        None
    """
    if bot.user:
        await bot.change_presence(
            status=discord.Status.offline,
            activity=discord.Activity(
            type=discord.ActivityType.playing,
            name="Moderating Discord Servers and Playing Minecraft"
            )
        )
        logger.info(f"Bot connected as {bot.user} (ID: {bot.user.id})")
    else:
        logger.warning("Bot connected, but user information not yet available.")
    
    # Start the rules cache refresh task
    logger.info("Starting server rules cache refresh task...")
    asyncio.create_task(bot_helper.refresh_rules_cache(bot, SERVER_RULES_CACHE))
    
    logger.info("Starting AI batch processing worker...")
    ai.start_batch_worker()
    logger.info("[AI] Batch processing worker started.")
    print("=============================================================")


@bot.event
async def on_message(message: discord.Message):
    """
    Processes incoming messages for AI-powered moderation.

    Args:
        message (discord.Message): The incoming message.

    Returns:
        None
    """
    # Ignore messages from bots and administrators to prevent loops and unwanted moderation.
    if message.author.bot or (isinstance(message.author, discord.Member) and message.author.guild_permissions.administrator):
        return

    # Store message in the channel's history for contextual analysis.
    hist = db_history[message.channel.id]
    hist.append({"role": "user", "content": message.content, "username": str(message.author)})

    # Get server rules for this guild (if available)
    server_rules = bot_helper.get_server_rules(message.guild.id, SERVER_RULES_CACHE) if message.guild else ""

    # Get a moderation action from the AI model with server rules
    action, reason = await ai.get_appropriate_action(
        current_message=message.content,
        history=list(hist),
        username=str(message.author),
        server_rules=server_rules
    )

    if action != ActionType.NULL:
        await bot_helper.take_action(action, reason, message, bot.user)


# ==========================================
# Main Entrypoint
# ==========================================
def main():
    """
    Main function to run the bot. Handles startup and fatal errors.

    Returns:
        None
    """
    if not DISCORD_BOT_TOKEN:
        logger.critical("FATAL: 'Mod_Bot_Token' environment variable not set. Bot cannot start.")
        return

    try:
        bot.run(DISCORD_BOT_TOKEN)
    except discord.LoginFailure:
        logger.critical("FATAL: Login failed. Please check if the bot token is correct.")
    except Exception as e:
        logger.critical(f"FATAL: An unexpected error occurred while running the bot: {e}")

if __name__ == "__main__":
    main()