"""
Discord Moderation Bot
======================

A Discord bot that uses an AI model to moderate chat, handle rule violations,
and provide server administration commands for manual moderation actions like
banning, kicking, and timing out users.
"""

import asyncio
import collections
import datetime
import os
from pathlib import Path
import discord
from discord import Option
from discord.ext import commands
from dotenv import load_dotenv
from actions import ActionType
import ai_model as ai
import bot_helper
from logger import get_logger

# ==========================================
# Configuration and Logging Setup
# ==========================================

# Use pathlib for robust path management
BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)

# Get logger for this module
logger = get_logger("bot")

# Load environment variables
load_dotenv()
DISCORD_BOT_TOKEN = os.getenv('Mod_Bot_Token')

# Server rules cache - will be populated dynamically from Discord channels
SERVER_RULES_CACHE = {}  # guild_id -> rules_text

# ==========================================
# Bot Initialization & State
# ==========================================
intents = discord.Intents.all()
intents.message_content = True

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
# Moderation Commands
# ==========================================

@mod_group.command(name="warn", description="Warn a user for a specified reason.")
async def warn(
    ctx: discord.ApplicationContext,
    user: Option(discord.Member, "The user to warn.", required=True),  # type: ignore
    reason: Option(str, "Reason for the warning.", default="No reason provided."),  # type: ignore
    delete_message_seconds: Option(
        int,
        "Delete messages from (choose time range)",
        choices=bot_helper.DELETE_MESSAGE_CHOICES,
        default=0
    )  # type: ignore
) -> None:
    """
    Issues a warning to a user, sends a DM notification, and optionally deletes recent messages.
    """
    if not bot_helper.has_permissions(ctx, manage_messages=True):
        await ctx.respond("You don't have permission to warn members.", ephemeral=True)
        return

    await ctx.defer()
    try:
        if not isinstance(user, discord.Member):
            return await ctx.followup.send("This user is not a member of the server.", ephemeral=True)
        if user.id == ctx.user.id:
            return await ctx.followup.send("You cannot warn yourself.", ephemeral=True)
        if user.guild_permissions.administrator:
            return await ctx.followup.send("You cannot warn an administrator.", ephemeral=True)

        # Send DM and embed first for immediate response
        await bot_helper.send_dm_and_embed(ctx, user, ActionType.WARN, reason)
        
        # Delete messages in the background if requested
        if delete_message_seconds > 0:
            asyncio.create_task(bot_helper.delete_messages_background(ctx, user, delete_message_seconds))
            
    except Exception as e:
        await bot_helper.handle_error(ctx, e)

@mod_group.command(name="timeout", description="Timeout a user for a specified duration.")
async def timeout(
    ctx: discord.ApplicationContext,
    user: Option(discord.Member, "The user to timeout.", required=True),  # type: ignore
    duration: Option(str, "Duration of the timeout.", choices=bot_helper.DURATION_CHOICES, default="10 mins"), # type: ignore
    reason: Option(str, "Reason for the timeout.", default="No reason provided."),  # type: ignore
    delete_message_seconds: Option(
        int,
        "Delete messages from (choose time range)",
        choices=bot_helper.DELETE_MESSAGE_CHOICES,
        default=0
    )  # type: ignore
) -> None:
    """
    Applies a timeout to a user, sends a DM notification, and optionally deletes recent messages.
    """
    if not bot_helper.has_permissions(ctx, moderate_members=True):
        await ctx.respond("You don't have permission to timeout members.", ephemeral=True)
        return

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
        # Send DM and embed first for immediate response
        await bot_helper.send_dm_and_embed(ctx, user, ActionType.TIMEOUT, reason, duration)
        
        # Delete messages in the background if requested
        if delete_message_seconds > 0:
            asyncio.create_task(bot_helper.delete_messages_background(ctx, user, delete_message_seconds))
    except Exception as e:
        await bot_helper.handle_error(ctx, e)

@mod_group.command(name="kick", description="Kick a user from the server.")
async def kick(
    ctx: discord.ApplicationContext,
    user: Option(discord.Member, "The user to kick.", required=True),  # type: ignore
    reason: Option(str, "Reason for the kick.", default="No reason provided."),  # type: ignore
    delete_message_seconds: Option(
        int,
        "Delete messages from (choose time range)",
        choices=bot_helper.DELETE_MESSAGE_CHOICES,
        default=0
    )  # type: ignore
) -> None:
    """
    Kicks a user from the server, sends a DM notification, and optionally deletes recent messages.
    """
    if not bot_helper.has_permissions(ctx, kick_members=True):
        await ctx.respond("You don't have permission to kick members.", ephemeral=True)
        return

    await ctx.defer()
    try:
        if not isinstance(user, discord.Member):
            return await ctx.followup.send("This user is not a member of the server.", ephemeral=True)
        if user.id == ctx.user.id:
            return await ctx.followup.send("You cannot kick yourself.", ephemeral=True)
        if user.guild_permissions.administrator:
            return await ctx.followup.send("You cannot kick an administrator.", ephemeral=True)

        # Send DM and embed first, then kick user
        await bot_helper.send_dm_and_embed(ctx, user, ActionType.KICK, reason)
        await user.kick(reason=reason)
        
        # Delete messages in the background if requested
        if delete_message_seconds > 0:
            asyncio.create_task(bot_helper.delete_messages_background(ctx, user, delete_message_seconds))
    except Exception as e:
        await bot_helper.handle_error(ctx, e)

@mod_group.command(name="ban", description="Ban a user from the server.")
async def ban(
    ctx: discord.ApplicationContext,
    user: Option(discord.Member, "The user to ban.", required=True),  # type: ignore
    duration: Option(str, "Duration of the ban.", choices=bot_helper.DURATION_CHOICES, default=bot_helper.PERMANENT_DURATION), # type: ignore
    reason: Option(str, "Reason for the ban.", default="No reason provided."),  # type: ignore
    delete_message_seconds: Option(
        int,
        "Delete messages from (choose time range)",
        choices=bot_helper.DELETE_MESSAGE_CHOICES,
        default=0
    )  # type: ignore
) -> None:
    """
    Bans a user from the server, optionally for a temporary duration.

    Args:
        ctx (discord.ApplicationContext): The context of the command.
        user (discord.Member): The user to ban.
        duration (str): Duration of the ban.
        reason (str): Reason for the ban.
        delete_message_seconds (int): Number of seconds of messages to delete.

    Returns:
        None
    """
    if not bot_helper.has_permissions(ctx, ban_members=True):
        await ctx.respond("You don't have permission to ban members.", ephemeral=True)
        return

    await ctx.defer()
    
    try:
        if not isinstance(user, discord.Member):
            return await ctx.followup.send("This user is not a member of the server.", ephemeral=True)
        if user.id == ctx.user.id:
            return await ctx.followup.send("You cannot ban yourself.", ephemeral=True)
        if user.guild_permissions.administrator:
            return await ctx.followup.send("You cannot ban an administrator.", ephemeral=True)

        duration_seconds: int = bot_helper.parse_duration_to_seconds(duration)
        
        # Send DM and embed first, then ban user
        await bot_helper.send_dm_and_embed(ctx, user, ActionType.BAN, reason, duration)
        await ctx.guild.ban(user, reason=reason)

        # Delete messages in the background if requested (separate from Discord's ban deletion)
        if delete_message_seconds > 0:
            asyncio.create_task(bot_helper.delete_messages_background(ctx, user, delete_message_seconds))

        if duration_seconds > 0:
            logger.info(f"Scheduling unban for {getattr(user, 'display_name', str(user))} in {duration_seconds} seconds.")
            asyncio.create_task(bot_helper.unban_later(ctx.guild, user.id, ctx.channel, duration_seconds, bot))
    except Exception as e:
        await bot_helper.handle_error(ctx, e)


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
            status=discord.Status.online,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="for rule violations"
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
    logger.info("=" * 60)


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

    logger.debug(f"Received message from {message.author}: {message.clean_content}")
    if message.author.bot or (isinstance(message.author, discord.Member) and message.author.guild_permissions.administrator):
        return

    # Skip empty messages or messages with only whitespace
    actual_content = message.clean_content
    if not actual_content:
        return

    # Store message in the channel's history for contextual analysis.
    hist = db_history[message.channel.id]
    hist.append({"role": "user", "content": actual_content, "username": str(message.author)})

    # Get server rules
    server_rules = bot_helper.get_server_rules(message.guild.id, SERVER_RULES_CACHE) if message.guild else ""

    # Get a moderation action from the AI model with server rules
    action, reason = await ai.get_appropriate_action(
        current_message=actual_content,
        history=list(hist),
        username=message.author.name,
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
    """
    logger.info("Starting Discord Moderation Bot...")
    
    if not DISCORD_BOT_TOKEN:
        logger.critical("FATAL: 'Mod_Bot_Token' environment variable not set. Bot cannot start.")
        return

    try:
        logger.info("Attempting to connect to Discord...")
        bot.run(DISCORD_BOT_TOKEN)
    except discord.LoginFailure:
        logger.critical("FATAL: Login failed. Please check if the bot token is correct.")
    except Exception as e:
        logger.critical(f"FATAL: An unexpected error occurred while running the bot: {e}", exc_info=True)

if __name__ == "__main__":
    main()