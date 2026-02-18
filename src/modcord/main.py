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

from modcord.listener import events_listener
from modcord.command import debug_cmds, guild_settings_cmds
from modcord.listener import message_listener
from modcord.database import database as db
from modcord.history.discord_history_fetcher import DiscordHistoryFetcher
from modcord.moderation.moderation_pipeline import ModerationPipeline
from modcord.services.message_processing_service import MessageProcessingService
from modcord.services.moderation_queue_service import ModerationQueueService
from modcord.settings.guild_settings_manager import guild_settings_manager
from modcord.scheduler.rules_sync_scheduler import rules_sync_scheduler
from modcord.scheduler.guidelines_sync_scheduler import guidelines_sync_scheduler
from modcord.ui.console import ConsoleControl, close_bot_instance, console_session
from modcord.util.logger import get_logger, handle_exception


logger = get_logger("main")


def load_environment() -> str:
    """
    Load environment variables from .env file and return the Discord bot token.
    
    Searches for a .env file in the base directory and loads all variables.
    Validates that the required DISCORD_BOT_TOKEN is present.
    
    Returns:
        str: Discord bot token extracted from the environment.
    
    Raises:
        SystemExit: If DISCORD_BOT_TOKEN is not set in the environment.
    """
    load_dotenv(dotenv_path=BASE_DIR / ".env")
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        logger.critical("'DISCORD_BOT_TOKEN' environment variable not set. Bot cannot start.")
        sys.exit(1)
    return token


def build_intents() -> discord.Intents:
    """
    Construct the Discord intents required for Modcord to function.
    
    Enables the following intents:
    - message_content: Read message text for moderation
    - guilds: Access guild information
    - messages: Receive message events
    - reactions: Handle reaction events
    - members: Access member information and events
    
    Returns:
        discord.Intents: Configured intents object for bot initialization.
    """
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.messages = True
    intents.reactions = True
    intents.members = True
    return intents


def load_cogs(discord_bot_instance: discord.Bot) -> ModerationQueueService:
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
    """
    # --- Build the service layer ------------------------------------------
    moderation_pipeline = ModerationPipeline(discord_bot_instance)
    history_fetcher = DiscordHistoryFetcher(discord_bot_instance)
    processing_service = MessageProcessingService(
        bot=discord_bot_instance,
        moderation_pipeline=moderation_pipeline,
        history_fetcher=history_fetcher,
    )
    queue_service = ModerationQueueService()
    # ----------------------------------------------------------------------

    debug_cmds.setup(discord_bot_instance)
    events_listener.setup(discord_bot_instance)
    message_listener.setup(discord_bot_instance, queue_service, processing_service)
    guild_settings_cmds.setup(discord_bot_instance)

    logger.info("[MAIN] All cogs loaded successfully.")

    return queue_service  # returned so shutdown_runtime can cancel workers


def create_bot() -> tuple[discord.Bot, ModerationQueueService]:
    """
    Create and initialize the Discord bot instance with all cogs loaded.

    Returns:
        A (bot, queue_service) tuple so the queue can be shut down cleanly.
    """
    bot = discord.Bot(intents=build_intents())
    queue_service = load_cogs(bot)
    return bot, queue_service


async def _start_schedulers_when_ready(bot: discord.Bot) -> None:
    """Wait for bot to be ready, then start background sync schedulers."""
    await bot.wait_until_ready()
    logger.info("[MAIN] Bot ready, starting background schedulers…")
    rules_sync_scheduler.start(bot)
    guidelines_sync_scheduler.start(bot)


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
        control (ConsoleControl): Console control for handling shutdown/restart requests.
    
    Returns:
        int: Exit code (0 for success, 1 for error).
    """
    logger.info("[MAIN] Attempting to run Discord bot with console control…")
    control.set_bot(bot)
    exit_code = 0

    try:
        async with console_session(control):
            # Start scheduler initialization task (runs after bot.wait_until_ready())
            scheduler_task = asyncio.create_task(_start_schedulers_when_ready(bot))
            try:
                await bot.start(token)
            except asyncio.CancelledError:
                logger.info("[MAIN] Discord bot start cancelled; shutting down")
            except Exception as exc:
                logger.critical("Discord bot runtime error: %s", exc)
                exit_code = 1
            finally:
                scheduler_task.cancel()
    finally:
        control.set_bot(None)
        await shutdown_runtime(bot, queue_service)

    return exit_code


async def shutdown_runtime(
    bot: discord.Bot,
    queue_service: ModerationQueueService | None = None,
) -> None:
    """
    Gracefully shutdown all Modcord subsystems and clean up resources.

    Shutdown order
    --------------
    1. Discord connection (stop receiving events)
    2. Per-channel queue workers (ModerationQueueService)
    3. Background schedulers
    4. Guild settings manager (persist pending changes)
    5. Database (WAL checkpoint + lock release)
    6. Garbage collection

    Args:
        bot: The bot instance to shut down.
        queue_service: Optional queue service whose workers need cancelling.
    """
    # First, close Discord connection to stop receiving events
    try:
        await close_bot_instance(bot, log_close=True)
        await bot.http.close()
    except Exception as exc:
        logger.exception("Error during discord http connection shutdown: %s", exc)

    # Cancel queue workers before stopping schedulers
    if queue_service is not None:
        try:
            await queue_service.shutdown()
        except Exception as exc:
            logger.exception("Error during queue service shutdown: %s", exc)

    # Stop background tasks in proper order
    try:
        await rules_sync_scheduler.shutdown()
    except Exception as exc:
        logger.exception("Error during rules sync scheduler shutdown: %s", exc)

    try:
        await guidelines_sync_scheduler.shutdown()
    except Exception as exc:
        logger.exception("Error during guidelines sync scheduler shutdown: %s", exc)

    # Persist any pending guild settings
    try:
        await guild_settings_manager.shutdown()
    except Exception as exc:
        logger.exception("Error during guild settings shutdown: %s", exc)

    # Checkpoint WAL and release database lock
    try:
        await db.database.shutdown()
    except Exception as exc:
        logger.exception("Error during database shutdown: %s", exc)

    # Final cleanup
    try:
        import gc
        gc.collect()
    except Exception as exc:
        logger.exception("Garbage collection during shutdown failed: %s", exc)
    
    # This should be the absolute last log message before exit
    logger.info("[MAIN] Shutdown complete.")


async def async_main() -> int:
    """
    Main async entry point that bootstraps and runs Modcord.
    
    Coordinates the complete startup sequence:
    1. Load environment variables and bot token
    2. Initialize database and load guild settings
    3. Create Discord bot instance and load cogs
    4. Initialize AI moderation engine
    5. Run bot with interactive console
    6. Handle restart requests
    
    Returns:
        int: Process exit code (0 for normal exit, 1 for error, -1 for restart).
    """
    token = load_environment()

    # Initialize database and load guild settings (bot will be passed later for auto-population)
    try:
        logger.info("[MAIN] Initializing database and loading guild settings...")
        await guild_settings_manager.async_init()
    except Exception as exc:
        logger.critical("Failed to initialize database: %s", exc)
        return 1

    try:
        bot, queue_service = create_bot()
    except Exception as exc:
        logger.critical("Failed to initialize Discord bot: %s", exc)
        return 1

    control = ConsoleControl()
    exit_code = await run_bot(bot, token, control, queue_service)

    if control.is_restart_requested():
        logger.info("[MAIN] Restart requested, returning exit code -1 to trigger restart")
        return -1

    return exit_code


def main() -> int:
    """
    Main entry point that runs the async event loop and handles process lifecycle.
    
    Executes the async_main coroutine and handles special exit codes:
    - Exit code -1 triggers a process restart using os.execv
    - Other exit codes are returned normally
    
    Handles KeyboardInterrupt for graceful shutdown and SystemExit for
    explicit exit requests.
    
    Returns:
        int: Process exit code to return to the operating system.
    """
    logger.info("[MAIN] Starting Discord Moderation Bot…")
    try:
        exit_code = asyncio.run(async_main())

        if exit_code == -1:
            logger.info("[MAIN] Restart requested; replacing current process with new instance.")
            # Use os.execv to replace the current process, preserving stdin/stdout/stderr
            # This ensures the interactive console continues working after restart
            os.execv(sys.executable, [sys.executable] + sys.argv)
            return 0

        return exit_code
    except KeyboardInterrupt:
        logger.info("[MAIN] Shutdown requested by user.")
        return 0
    except SystemExit as exit_exc:
        code = exit_exc.code
        if isinstance(code, int):
            return code
        if code is None:
            return 1
        try:
            return int(code)
        except (ValueError, TypeError):
            logger.warning("[MAIN] SystemExit.code is not an int (%r); defaulting to 1", code)
            return 1
    except Exception as exc:
        logger.critical("An unexpected error occurred while running the bot: %s", exc)
        return 1


if __name__ == "__main__":
    sys.excepthook = handle_exception
    print(f"Exited with code: {main()}")