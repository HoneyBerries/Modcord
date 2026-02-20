"""
======================
Discord Moderation Bot
======================

A Discord bot that uses an AI model to moderate chat, handle rule violations,
and provide server administration commands for manual moderation actions like
banning, kicking, and timing out users.
"""

import os
import sys
from pathlib import Path

def resolve_base_dir() -> Path:
    """
    Determine the base directory of the Modcord project.
    
    This function resolves the project root using multiple strategies to support
    both development and compiled/deployed environments:
    
    1. MODCORD_HOME environment variable, if set
    2. Executable's directory if running as compiled/frozen binary (PyInstaller, Nuitka)
    3. Grandparent of this file's directory if running from source
    
    Returns:
        Path: Resolved absolute path to the project base directory.
    
    Note:
        The base directory is used as the working directory for the application.
    """
    if env_home := os.getenv("MODCORD_HOME"):
        return Path(env_home).resolve()

    if getattr(sys, "frozen", False) or getattr(sys, "compiled", False):
        return Path(sys.argv[0]).resolve().parent

    return Path(__file__).resolve().parents[2]

BASE_DIR = resolve_base_dir()
os.chdir(BASE_DIR)

# ______________________________________________________________
# Now that the base directory is set, import the rest of 
# Modcord and run the program
# ______________________________________________________________

import asyncio
import discord
from dotenv import load_dotenv

from modcord.cog.commands import debug_cmds, settings_cmds
from modcord.cog.listener import message_listener, events_listener, scheduler_cog
from modcord.database import database as db
from modcord.moderation.moderation_pipeline import ModerationPipeline
from modcord.services.message_processing_service import MessageProcessingService
from modcord.services.moderation_queue_service import ModerationQueueService
from modcord.settings.guild_settings_manager import guild_settings_manager
from modcord.console.control_panel import ConsoleControl, console_session
from modcord.util.logger import get_logger, handle_exception
from modcord.configuration.app_configuration import app_config


logger = get_logger("main")


def load_environment() -> tuple[str | None, str | None]:
    """
    Load environment variables from .env file and return tokens.
    
    Searches for a .env file in the base directory and loads all variables.
    
    Returns:
        tuple[str | None, str | None]: (discord_bot_token, openai_api_key)
    """
    load_dotenv(dotenv_path=BASE_DIR / ".env")
    bot_token = os.getenv("DISCORD_BOT_TOKEN")
    openai_api_key = os.getenv("OPENAI_API_KEY")

    return bot_token, openai_api_key



def load_cogs(discord_bot_instance: discord.Bot, openai_api_key: str) -> ModerationQueueService:
    """
    Register all Modcord cogs with the Discord bot instance.

    Service wiring happens here so every dependency is constructed in one
    place and injected transparently into the cogs that need them.

    Cogs loaded
    -----------
    - debug_cmds           : debug and testing commands
    - events_listener      : bot lifecycle (on_ready, guild join/leave)
    - message_listener     : thin event forwarder → queue service
    - guild_settings_cmds  : guild-specific settings management
    - moderation_cmds      : manual moderation commands

    Args:
        discord_bot_instance: The bot instance to attach cogs to.
        openai_api_key: The OpenAI-compatible API key.
    """
    # --- Build the service layer ------------------------------------------
    ai_settings = app_config.ai_settings
    moderation_pipeline = ModerationPipeline(
        bot=discord_bot_instance,
        api_key=openai_api_key,
        api_url=ai_settings.base_url,
    )
    processing_service = MessageProcessingService(
        bot=discord_bot_instance,
        moderation_pipeline=moderation_pipeline)
    queue_service = ModerationQueueService()
    # ----------------------------------------------------------------------

    debug_cmds.setup(discord_bot_instance)
    events_listener.setup(discord_bot_instance)
    message_listener.setup(discord_bot_instance, queue_service, processing_service)
    settings_cmds.setup(discord_bot_instance)
    scheduler_cog.setup(discord_bot_instance)

    logger.info("[MAIN] All cogs loaded successfully.")

    return queue_service  # returned so shutdown_runtime can cancel workers


def create_bot(openai_api_key: str) -> tuple[discord.Bot, ModerationQueueService]:
    """
    Create and initialize the Discord bot instance with all cogs loaded.

    Args:
        openai_api_key: The OpenAI-compatible API key.

    Returns:
        A (bot, queue_service) tuple so the queue can be shut down cleanly.
    """

    bot_intents = discord.Intents.default()
    bot_intents.message_content = True
    bot_intents.guilds = True
    bot_intents.messages = True
    bot_intents.reactions = True
    bot_intents.members = True

    bot = discord.Bot(intents=bot_intents)
    queue_service = load_cogs(bot, openai_api_key)
    return bot, queue_service



async def run_bot(
    bot: discord.Bot,
    token: str,
    control: ConsoleControl,
    queue_service: ModerationQueueService,
) -> int:
    """
    Run the Discord bot within the console session and return an exit code.
    
    Starts the bot, integrates with the interactive console for lifecycle control,
    and handles graceful shutdown of all subsystems when the bot stops.
    
    Args:
        bot (discord.Bot): The initialized bot instance to run.
        token (str): Discord bot authentication token.
        control (ConsoleControl): Console control for shutdown signalling.
        queue_service (ModerationQueueService): Queue service for background workers.

    Returns:
        int: Exit code (0 for success, 1 for error).
    """
    logger.info("[MAIN] Attempting to run Discord bot with console control…")
    control.set_bot(bot)
    exit_code = 0

    try:
        async with console_session(control):
            try:
                await bot.start(token)
            except asyncio.CancelledError:
                logger.info("[MAIN] Discord bot start cancelled; shutting down")
            except Exception as exc:
                logger.critical("Discord bot runtime error: %s", exc)
                exit_code = 1
    finally:
        control.set_bot(None)
        await shutdown_runtime(queue_service)

    return exit_code


async def shutdown_runtime(
    queue_service: ModerationQueueService,
) -> None:
    """Gracefully shut down all Modcord subsystems."""
    if queue_service is not None:
        await queue_service.shutdown()

    await db.database.shutdown()

    logger.info("[MAIN] Shutdown complete.")


async def async_main() -> int:
    """
    Main async entry point that bootstraps and runs Modcord.
    
    Coordinates the complete startup sequence:
    1. Load environment variables and bot token
    2. Initialize database and load guild settings
    3. Create a Discord bot instance and load cogs
    4. Initialize AI moderation engine
    5. Run bot with an interactive console

    Returns:
        int: Process exit code (0 for normal exit, 1 for error).
    """
    discord_bot_token, openai_api_key = load_environment()

    if not discord_bot_token:
        logger.critical("'DISCORD_BOT_TOKEN' environment variable not set. Bot cannot start.")
        return 1

    if not openai_api_key:
        logger.warning("'OPENAI_API_KEY' environment variable not set. AI moderation will fail if triggered.")

    # Initialize a database and load guild settings (bot will be passed later for auto-population)
    try:
        logger.info("[MAIN] Initializing database and loading guild settings...")
        await guild_settings_manager.async_init()
    except Exception as exc:
        logger.critical("Failed to initialize database: %s", exc)
        return 1

    try:
        bot, queue_service = create_bot(openai_api_key or "EMPTY")
    except Exception as exc:
        logger.critical("Failed to initialize Discord bot: %s", exc)
        return 1

    control = ConsoleControl()
    exit_code = await run_bot(bot, discord_bot_token, control, queue_service)

    return exit_code


def main() -> int:
    """
    Main entry point that runs the async event loop and handles the process lifecycle.

    Executes the async_main coroutine and returns the exit code.

    Handles KeyboardInterrupt for graceful shutdown and SystemExit for
    explicit exit requests.
    
    Returns:
        int: Process exit code to return to the operating system.
    """
    logger.info("[MAIN] Starting Discord Moderation Bot…")
    try:
        exit_code = asyncio.run(async_main())
        return exit_code

    except KeyboardInterrupt:
        logger.info("[MAIN] Shutdown requested by user.")
        return 0

    except SystemExit as exit_exc:
        code = exit_exc.code
        return code

    except Exception as exc:
        logger.critical("An unexpected error occurred while running the bot: %s", exc)
        return 1


if __name__ == "__main__":
    sys.excepthook = handle_exception
    print(f"Exited with code: {main()}")