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

import ai_model as ai

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

# Define necessary intents. Explicitly listing intents is better than `Intents.all()`.
intents = discord.Intents.all()


bot = discord.Bot(intents=intents)

# Per-channel chat history, using a defaultdict with a deque for efficient, capped storage.
# This provides conversational context for the AI model.
db_history = collections.defaultdict(lambda: collections.deque(maxlen=50))

# ==========================================
# Utility Functions
# ==========================================

def parse_duration_to_seconds(duration_str: str) -> int:
    """
    Parses a human-readable duration string into seconds.
    Returns 0 if the duration is permanent ("Till the end of time").
    """
    mapping = {
        "60 secs": 60,
        "5 mins": 5 * 60,
        "10 mins": 10 * 60,
        "30 mins": 30 * 60,
        "1 hour": 60 * 60,
        "2 hours": 2 * 60 * 60,
        "1 day": 24 * 60 * 60,
        "1 week": 7 * 24 * 60 * 60,
        "Till the end of time": 0,
    }
    return mapping.get(duration_str, 0)


async def send_dm_to_user(user: discord.Member, message: str) -> bool:
    """
    Sends a direct message to a user and handles potential errors.
    Returns True if the DM was sent successfully, False otherwise.
    """
    try:
        await user.send(message)
        return True
    except discord.Forbidden:
        logger.warning(f"Could not DM {user.display_name}: They may have DMs disabled.")
    except Exception as e:
        logger.error(f"Failed to send DM to {user.display_name}: {e}")
    return False

# ==========================================
# Embed Builder
# ==========================================

async def create_punishment_embed(
    action_type: str,
    user: discord.User | discord.Member,
    reason: str,
    duration_str: str | None = None,
    issuer: discord.User | discord.Member | discord.ClientUser | None = None
) -> discord.Embed:
    """
    Creates a standardized embed for logging moderation actions.
    """
    # Define colors and emojis for different actions to provide quick visual cues.
    action_details = {
        "Ban": {"color": discord.Color.red(), "emoji": "🔨"},
        "Kick": {"color": discord.Color.orange(), "emoji": "👢"},
        "Warn": {"color": discord.Color.yellow(), "emoji": "⚠️"},
        "Mute": {"color": discord.Color.blue(), "emoji": "🔇"},
        "Timeout": {"color": discord.Color.blue(), "emoji": "⏱️"},
        "Unban": {"color": discord.Color.green(), "emoji": "🔓"},
    }
    details = action_details.get(action_type, {"color": discord.Color.light_grey(), "emoji": "❓"})

    embed = discord.Embed(
        title=f"{details['emoji']} {action_type} Issued",
        color=details['color'],
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    embed.add_field(name="User", value=f"{user.mention} (`{user.id}`)", inline=True)
    embed.add_field(name="Action", value=action_type, inline=True)
    if issuer:
        embed.add_field(name="Moderator", value=issuer.mention, inline=True)

    embed.add_field(name="Reason", value=reason, inline=False)

    if duration_str and duration_str != "Till the end of time":
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

    embed.set_footer(text=f"Bot: {bot.user.name if bot.user else 'ModBot'}")
    return embed

# ==========================================
# Moderation Action Handler
# ==========================================

async def take_action(action: str, reason: str, message: discord.Message):
    """
    Applies a disciplinary action to the author of a message based on AI output.
    This function is designed for automated actions.
    """
    if action == "null" or not message.guild or not isinstance(message.author, discord.Member):
        return

    user = message.author
    guild = message.guild
    channel = message.channel
    action = action.lower()

    logger.info(f"AI action triggered: '{action}' on user {user.display_name} for reason: '{reason}'")

    try:
        if action == "delete":
            await message.delete()
            logger.info(f"Deleted message from {user.display_name}.")
            return # Deletion is a standalone action.

        # Prepare DM and embed for other actions.
        dm_message = ""
        embed = None

        if action == "ban":
            dm_message = f"You have been banned from {guild.name}.\n**Reason**: {reason}"
            await send_dm_to_user(user, dm_message)
            await message.delete()
            await guild.ban(user, reason=f"AI Mod: {reason}")
            embed = await create_punishment_embed("Ban", user, reason, "Till the end of time", bot.user)

        elif action == "kick":
            dm_message = f"You have been kicked from {guild.name}.\n**Reason**: {reason}"
            await send_dm_to_user(user, dm_message)
            await message.delete()
            await guild.kick(user, reason=f"AI Mod: {reason}")
            embed = await create_punishment_embed("Kick", user, reason, issuer=bot.user)

        elif action in ("timeout", "mute"):
            duration_seconds = 10 * 60  # Default 10 minutes for AI timeouts.
            duration_str = "10 mins"
            until = discord.utils.utcnow() + datetime.timedelta(seconds=duration_seconds)
            dm_message = f"You have been timed out in {guild.name} for {duration_str}.\n**Reason**: {reason}"
            await user.timeout(until, reason=f"AI Mod: {reason}")
            await send_dm_to_user(user, dm_message)
            embed = await create_punishment_embed("Timeout", user, reason, duration_str, bot.user)

        elif action == "warn":
            dm_message = f"You have received a warning in {guild.name}.\n**Reason**: {reason}"
            await send_dm_to_user(user, dm_message)
            embed = await create_punishment_embed("Warn", user, reason, issuer=bot.user)

        if embed and isinstance(channel, (discord.TextChannel, discord.Thread)):
            await channel.send(embed=embed)

    except discord.Forbidden:
        logger.warning(f"Failed to execute '{action}' on {user.display_name}: Missing permissions.")
    except Exception as e:
        logger.error(f"Error executing action '{action}' on {user.display_name}: {e}", exc_info=True)


# ==========================================
# Scheduled Unban Helper
# ==========================================

async def unban_later(guild: discord.Guild, user_id: int, channel: discord.abc.Messageable, duration_seconds: int):
    """Schedules a user to be unbanned after a specified duration."""
    await asyncio.sleep(duration_seconds)
    try:
        user_obj = discord.Object(id=user_id)
        await guild.unban(user_obj, reason="Ban duration expired.")
        logger.info(f"Unbanned user {user_id} after ban expired.")

        if isinstance(channel, (discord.TextChannel, discord.Thread)):
            # Try to fetch user for a richer embed, but fall back if they are not found.
            user = await bot.fetch_user(user_id)
            embed = await create_punishment_embed("Unban", user, "Ban duration expired.", issuer=bot.user)
            await channel.send(embed=embed)
    except discord.NotFound:
        logger.warning(f"Could not unban user {user_id}: User not found in ban list.")
    except Exception as e:
        logger.error(f"Failed to auto-unban user {user_id}: {e}")

# ==========================================
# Server Rules Management
# ==========================================

async def fetch_server_rules_from_channel(guild: discord.Guild) -> str:
    rule_keywords = ["guidelines", "regulations", "policy", "policies", "server-rules", "rule"]  # updated
    messages = []
    for channel in guild.text_channels:
        channel_name_lower = channel.name.lower()
        if any(keyword in channel_name_lower for keyword in rule_keywords):
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

async def refresh_rules_cache():
    """
    Periodically refresh the server rules cache for all guilds.
    """
    while True:
        try:
            logger.info("Refreshing server rules cache...")
            
            for guild in bot.guilds:
                try:
                    rules_text = await fetch_server_rules_from_channel(guild)
                    SERVER_RULES_CACHE[guild.id] = rules_text
                    
                    if rules_text:
                        logger.info(f"Cached rules for {guild.name} ({len(rules_text)} characters)")
                    else:
                        logger.warning(f"No rules found for {guild.name}")
                        
                except Exception as e:
                    logger.error(f"Failed to fetch rules for {guild.name}: {e}")
                    # Keep existing cache if fetch fails
                    if guild.id not in SERVER_RULES_CACHE:
                        SERVER_RULES_CACHE[guild.id] = ""
            
            logger.info(f"Rules cache refreshed for {len(SERVER_RULES_CACHE)} guilds")
            
        except Exception as e:
            logger.error(f"Error during rules cache refresh: {e}")
        
        # Wait 5 minutes before next refresh (avoid hitting rate limits)
        await asyncio.sleep(300)

def get_server_rules(guild_id: int) -> str:
    """
    Get cached server rules for a guild.
    Returns empty string if no rules are cached.
    """
    return SERVER_RULES_CACHE.get(guild_id, "")

# ==========================================
# Slash Commands
# ==========================================

@bot.slash_command(name="test", description="Checks if the bot is online and its latency.")
async def test(ctx: discord.ApplicationContext):
    """A simple health-check command."""
    latency_ms = bot.latency * 1000
    await ctx.respond(f":white_check_mark: I am online and working!\n**Latency**: {latency_ms:.2f} ms.", ephemeral=True)

# Create a command group for moderation commands for better organization.
mod_group = bot.create_group("mod", "Moderation commands")
debug_group = bot.create_group("debug", "Debugging commands")

# ==========================================
# Moderation Command Error Handler
# ==========================================
from discord.ext.commands.errors import MissingPermissions

@mod_group.error
async def mod_group_error_handler(ctx, error):
    if isinstance(error, MissingPermissions):
        await ctx.respond(
            "❌ You do not have the required permissions to use this command.", ephemeral=True
        )
    else:
        logger.error(f"Error in moderation command: {type(error).__name__}: {error}", exc_info=True)
        await ctx.respond(
            "❌ An unexpected error occurred while processing your moderation command.", ephemeral=True
        )


@mod_group.command(name="warn", description="Warn a user for a specified reason.")
@commands.has_permissions(manage_messages=True)
async def warn(
    ctx: discord.ApplicationContext,
    user: Option(discord.Member, "The user to warn.", required=True),  # type: ignore
    reason: Option(str, "Reason for the warning.", default="Breaking server rules")  # type: ignore
):
    
    # Immediately acknowledge the interaction
    await ctx.defer()

    try:
        dm_message = f"You have been warned in {ctx.guild.name}.\n**Reason**: {reason}"
        await send_dm_to_user(user, dm_message)

        embed = await create_punishment_embed("Warn", user, reason, issuer=ctx.user)
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
    duration: Option(str, "Duration of the timeout.", choices=[  # type: ignore
        "60 secs", "5 mins", "10 mins", "30 mins", "1 hour", "2 hours", "1 day"], default="10 mins"),
    reason: Option(str, "Reason for the timeout.", default="No reason provided.")  # type: ignore
):
    # Immediately acknowledge the interaction
    await ctx.defer()
    try:
        if not isinstance(user, discord.Member):
            return await ctx.followup.send("This user is not a member of the server.", ephemeral=True)
        if user.id == ctx.user.id:
            return await ctx.followup.send("You cannot timeout yourself.", ephemeral=True)
        if user.guild_permissions.administrator:
            return await ctx.followup.send("You cannot timeout an administrator.", ephemeral=True)

        duration_seconds = parse_duration_to_seconds(duration)
        until = discord.utils.utcnow() + datetime.timedelta(seconds=duration_seconds)

        await user.timeout(until, reason=reason)
        dm_message = f"You have been timed out in {ctx.guild.name} for {duration}.\n**Reason**: {reason}"
        await send_dm_to_user(user, dm_message)
        embed = await create_punishment_embed("Timeout", user, reason, duration, ctx.user)
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
):
    # Immediately acknowledge the interaction
    await ctx.defer()
    
    try:
        if not isinstance(user, discord.Member):
            return await ctx.followup.send("This user is not a member of the server.", ephemeral=True)
        if user.id == ctx.user.id:
            return await ctx.followup.send("You cannot kick yourself.", ephemeral=True)
        if user.guild_permissions.administrator:
            return await ctx.followup.send("You cannot kick an administrator.", ephemeral=True)

        dm_message = f"You have been kicked from {ctx.guild.name}.\n**Reason**: {reason}"
        await send_dm_to_user(user, dm_message)
        await user.kick(reason=reason)
        embed = await create_punishment_embed("Kick", user, reason, issuer=ctx.user)
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
    duration: Option(str, "Duration of the ban.", choices=[  # type: ignore
        "60 secs", "5 mins", "10 mins", "1 hour", "1 day", "1 week", "Till the end of time"], default="Till the end of time"),
    reason: Option(str, "Reason for the ban.", default="No reason provided."),  # type: ignore
    delete_message_days: Option(int, "Number of days of messages to delete (0-7).", choices=[0, 1, 7], default=1)  # type: ignore
):
    # Immediately acknowledge the interaction
    await ctx.defer()
    
    try:
        if not isinstance(user, discord.Member):
            return await ctx.followup.send("This user is not a member of the server.", ephemeral=True)
        if user.id == ctx.user.id:
            return await ctx.followup.send("You cannot ban yourself.", ephemeral=True)
        if user.guild_permissions.administrator:
            return await ctx.followup.send("You cannot ban an administrator.", ephemeral=True)

        duration_seconds = parse_duration_to_seconds(duration)
        dm_message = f"You have been banned from {ctx.guild.name} for: {duration}.\n**Reason**: {reason}"
        await send_dm_to_user(user, dm_message)
        await ctx.guild.ban(user, reason=reason, delete_message_days=delete_message_days)
        embed = await create_punishment_embed("Ban", user, reason, duration, ctx.user)
        await ctx.followup.send(embed=embed)

        # If the ban is temporary, schedule the unban task.
        if duration_seconds > 0:
            logger.info(f"Scheduling unban for {getattr(user, 'display_name', str(user))} in {duration_seconds} seconds.")
            asyncio.create_task(unban_later(ctx.guild, user.id, ctx.channel, duration_seconds))
    except discord.Forbidden:
        await ctx.followup.send("I do not have permissions to ban this user.", ephemeral=True)
    except AttributeError:
        await ctx.followup.send("Failed: Target is not a valid server member.", ephemeral=True)
    except Exception as e:
        logger.error(f"Failed to ban {getattr(user, 'display_name', str(user))}: {e}")
        await ctx.followup.send("An unexpected error occurred.", ephemeral=True)


# ==========================================
# Debugging Commands (because they are good 4 u)
# ==========================================
@debug_group.command(name="refresh_rules", description="Manually refresh the server rules cache.")
@commands.has_permissions(administrator=True)
async def refresh_rules_command(ctx: discord.ApplicationContext):
    """Manually refresh the server rules cache for this guild."""
    await ctx.defer()
    
    try:
        rules_text = await fetch_server_rules_from_channel(ctx.guild)
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
    """Display the current cached server rules."""
    await ctx.defer()
    
    rules_text = get_server_rules(ctx.guild.id)
    
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
    """Fired when the bot successfully connects to Discord."""
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
    asyncio.create_task(refresh_rules_cache())
    
    logger.info("Starting AI batch processing worker...")
    ai.start_batch_worker()
    logger.info("[AI] Batch processing worker started.")
    print("=============================================================")


@bot.event
async def on_message(message: discord.Message):
    """
    Processes incoming messages for AI-powered moderation.
    """
    # Ignore messages from bots and administrators to prevent loops and unwanted moderation.
    if message.author.bot or (isinstance(message.author, discord.Member) and message.author.guild_permissions.administrator):
        return

    # Store message in the channel's history for contextual analysis.
    hist = db_history[message.channel.id]
    hist.append({"role": "user", "content": message.content, "username": str(message.author)})

    # Get server rules for this guild (if available)
    server_rules = get_server_rules(message.guild.id) if message.guild else ""

    # Get a moderation action from the AI model with server rules
    action_response = await ai.get_appropriate_action(
        current_message=message.content,
        history=list(hist),
        username=str(message.author),
        server_rules=server_rules
    )

    # Parse the AI's response (e.g., "ban:Spamming")
    if ":" in action_response:
        action, reason = action_response.split(":", 1)
        action = action.strip().lower()
        reason = reason.strip()
    else:
        # If the response is not in the expected format, default to no action.
        action, reason = "null", "AI model response format error"

    if action != "null":
        await take_action(action, reason, message)

# ==========================================
# Main Entrypoint
# ==========================================
def main():
    """Main function to run the bot."""
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