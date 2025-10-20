"""
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
    """Determine the base directory of the project. Designed for compiled/bundled execution.
    Resolution order:
    1. MODCORD_HOME environment variable, if set.
    2. If running in a frozen/compiled context (e.g., PyInstaller, Nuitka), use the executable's directory.
    3. Otherwise, assume running from source and use the grandparent of this file's directory.
    """
    if env_home := os.getenv("MODCORD_HOME"):
        return Path(env_home).resolve()

    if getattr(sys, "frozen", False) or getattr(sys, "compiled", False):
        return Path(sys.argv[0]).resolve().parent

    return Path(__file__).resolve().parents[2]

BASE_DIR = resolve_base_dir()
os.chdir(BASE_DIR)

import asyncio
import discord
from dotenv import load_dotenv

from modcord.ai.ai_moderation_processor import model_state
from modcord.ai.ai_lifecycle import (
    initialize_engine,
    shutdown_engine,
)
from modcord.configuration.guild_settings import guild_settings_manager
from modcord.util.message_cache import message_history_cache, initialize_cache_from_config
from modcord.ui.console import ConsoleControl, close_bot_instance, console_session
from modcord.util.logger import get_logger, handle_exception


logger = get_logger("main")


def load_environment() -> str:
    """Load environment variables and return the Discord bot token.

    Returns
    -------
    str
        Discord bot token extracted from the loaded environment.

    Raises
    ------
    SystemExit
        If the required ``DISCORD_BOT_TOKEN`` variable is missing.
    """
    load_dotenv(dotenv_path=BASE_DIR / ".env")
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        logger.critical("'DISCORD_BOT_TOKEN' environment variable not set. Bot cannot start.")
        sys.exit(1)
    return token


def build_intents() -> discord.Intents:
    """Construct the Discord intents required for Modcord runtime features.

    Returns
    -------
    discord.Intents
        Intents enabling guild, member, message, and reaction events.
    """
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.messages = True
    intents.reactions = True
    intents.members = True
    return intents


def load_cogs(discord_bot_instance: discord.Bot) -> None:
    """Register all operational cogs with the provided Discord bot instance.

    Parameters
    ----------
    discord_bot_instance:
        Py-Cord bot object that should receive the Modcord cogs.
    """
    from modcord.bot.cogs import debug_cmds, guild_settings_cmds, moderation_cmds, events_listener, message_listener

    debug_cmds.setup(discord_bot_instance)
    events_listener.setup(discord_bot_instance)
    message_listener.setup(discord_bot_instance)
    guild_settings_cmds.setup(discord_bot_instance)
    moderation_cmds.setup(discord_bot_instance)

    logger.info("All cogs loaded successfully.")


def create_bot() -> discord.Bot:
    """Instantiate the Discord bot and register all cogs."""
    bot = discord.Bot(intents=build_intents())
    load_cogs(bot)
    # Wire the bot into the message cache for Discord API fallback
    message_history_cache.set_bot(bot)
    return bot


async def initialize_ai_model() -> None:
    """Initialize the AI moderation engine prior to connecting the Discord client.

    Raises
    ------
    Exception
        Propagated when the underlying initializer encounters an unexpected failure.
    """
    try:
        from modcord.configuration.app_configuration import app_config
        # Configure message cache from app_config
        initialize_cache_from_config(app_config)
        
        logger.info("Initializing AI moderation engine before bot startup…")
        available, detail = await initialize_engine()
        if detail and not available:
            logger.critical("AI model failed to initialize: %s", detail)
    except Exception as exc:
        logger.critical("Unexpected error during AI initialization: %s", exc)
        raise


async def start_bot(bot: discord.Bot, token: str) -> None:
    """Start the Discord bot and handle lifecycle logging around the connection.

    Parameters
    ----------
    bot:
        Discord client to start.
    token:
        Authentication token used to connect to Discord.
    """
    logger.info("Attempting to connect to Discord…")
    try:
        await bot.start(token)
    except asyncio.CancelledError:
        logger.info("Discord bot start cancelled; shutting down")
    finally:
        logger.info("Discord bot start routine finished.")


async def shutdown_runtime(bot: discord.Bot | None = None) -> None:
    """Gracefully stop the Discord bot, AI engine, and guild settings manager.

    Parameters
    ----------
    bot:
        Optional bot instance to close before shutting down subsystems.
    """
    await close_bot_instance(bot, log_close=True)

    await bot.http.close() # type: ignore

    try:
        await shutdown_engine()
    except Exception as exc:
        logger.exception("Error during moderation processor shutdown: %s", exc)

    try:
        await guild_settings_manager.shutdown()
    except Exception as exc:
        logger.exception("Error during guild settings shutdown: %s", exc)
    
    logger.info("Shutdown complete.")


async def run_bot_session(bot: discord.Bot, token: str, control: ConsoleControl) -> int:
    """Run the bot alongside the console, returning an exit code."""
    control.set_bot(bot)
    exit_code = 0

    try:
        async with console_session(control):
            try:
                await start_bot(bot, token)
            except asyncio.CancelledError:
                logger.info("Bot start cancelled; proceeding to shutdown")
            except Exception as exc:
                logger.critical("Discord bot runtime error: %s", exc)
                exit_code = 1
    finally:
        control.set_bot(None)
        await shutdown_runtime(bot)

    return exit_code


async def async_main() -> int:
    """Bootstrap the bot, console, and AI engine, returning an exit code.

    Returns
    -------
    int
        Process exit code reflecting success or failure of initialization.
    """
    token = load_environment()

    # Initialize database and load guild settings
    try:
        logger.info("Initializing database and loading guild settings...")
        await guild_settings_manager.async_init()
    except Exception as exc:
        logger.critical("Failed to initialize database: %s", exc)
        return 1

    try:
        bot = create_bot()
    except Exception as exc:
        logger.critical("Failed to initialize Discord bot: %s", exc)
        return 1

    try:
        await initialize_ai_model()
    except Exception:
        if model_state.init_error:
            logger.critical("AI initialization failed irrecoverably: %s", model_state.init_error)
        await shutdown_runtime(bot)
        return 1

    if not model_state.available:
        logger.warning(
            "AI model is unavailable (%s). Continuing without automated moderation.",
            model_state.init_error or "no details",
        )

    control = ConsoleControl()
    exit_code = await run_bot_session(bot, token, control)

    if control.is_restart_requested():
        logger.info("Restart requested, returning exit code 42 to trigger restart")
        return 42

    return exit_code


def main() -> int:
    """Entrypoint that orchestrates the async runtime and returns the process code.

    Returns
    -------
    int
        Exit code propagated to the operating system. Returns 42 to trigger a restart.
    """
    logger.info("Starting Discord Moderation Bot…")
    try:
        exit_code = asyncio.run(async_main())

        if exit_code == 42:
            logger.info("Restart requested; replacing current process with new instance.")
            # Use os.execv to replace the current process, preserving stdin/stdout/stderr
            # This ensures the interactive console continues working after restart
            os.execv(sys.executable, [sys.executable] + sys.argv)
            # execv never returns; the following is unreachable but satisfies type checkers
            return 0  # pragma: no cover

        return exit_code
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user.")
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
            logger.warning("SystemExit.code is not an int (%r); defaulting to 1", code)
            return 1
    except Exception as exc:
        logger.critical("An unexpected error occurred while running the bot: %s", exc)
        return 1


if __name__ == "__main__":
    sys.excepthook = handle_exception
    print(f"Exited with code: {main()}")