"""
Discord Moderation Bot
======================

A Discord bot that uses an AI model to moderate chat, handle rule violations,
and provide server administration commands for manual moderation actions like
banning, kicking, and timing out users.

Refactored version using cogs for better organization and maintainability.
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
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.shortcuts import PromptSession
from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import FormattedText

from modcord.ai.ai_moderation_processor import model_state
from modcord.ai.ai_lifecycle import (
    initialize_engine,
    restart_engine,
    shutdown_engine,
)
from modcord.bot.cogs import events_listener
from modcord.configuration.guild_settings import guild_settings_manager
from modcord.util.logger import get_logger, handle_exception

# Set the base directory to the project root


def console_print(message: str, style: str = "") -> None:
    """Print a message to console using prompt_toolkit to avoid interfering with prompts.
    
    Parameters
    ----------
    message:
        Text to display in the console.
    style:
        Optional ANSI color code (e.g., 'ansigreen', 'ansired'). If empty, no styling is applied.
    """
    if style:
        formatted_text = FormattedText([(style, message)])
    else:
        formatted_text = message
    print_formatted_text(formatted_text)


# Get logger for this module
logger = get_logger("main")


class ConsoleControl:
    """Manage console-driven lifecycle controls for the running Discord bot.

    This helper centralizes access to the live bot instance, coordinates restart
    locks, and exposes shutdown events to the interactive console layer.
    """

    def __init__(self) -> None:
        """Initialize synchronization primitives for console and bot coordination."""
        self.shutdown_event = asyncio.Event()
        self.restart_lock = asyncio.Lock()
        self._bot: discord.Bot | None = None

    def set_bot(self, bot: discord.Bot | None) -> None:
        """Register or clear the active bot reference for console operations.

        Parameters
        ----------
        bot:
            Discord bot instance to associate with the console, or ``None`` to clear the reference.
        """
        self._bot = bot

    @property
    def bot(self) -> discord.Bot | None:
        """Return the currently tracked Discord bot instance, if any."""
        return self._bot

    def request_shutdown(self) -> None:
        """Signal all console consumers to begin a coordinated shutdown."""
        self.shutdown_event.set()

    def stop(self) -> None:
        """Compatibility alias that triggers a console-initiated shutdown."""
        self.shutdown_event.set()

    def is_shutdown_requested(self) -> bool:
        """Return ``True`` when a shutdown signal has been issued via the console."""
        return self.shutdown_event.is_set()


async def restart_ai_engine(control: ConsoleControl) -> None:
    """Restart the moderation engine and refresh the bot's presence indicators.

    Parameters
    ----------
    control:
        Console management helper providing access to the restart lock and bot reference.
    """
    async with control.restart_lock:
        console_print("Restarting AI moderation engine…")
        try:
            available, detail = await restart_engine()
        except Exception as exc:
            logger.exception("Error while restarting AI engine: %s", exc)
            available = False
            detail = str(exc)

        bot = control.bot
        if bot is not None:
            events_cog = bot.get_cog("EventsListenerCog")
            updater = getattr(events_cog, "update_presence_for_model_state", None)
            if callable(updater):
                try:
                    maybe_coro = updater()
                    if asyncio.iscoroutine(maybe_coro):
                        await maybe_coro
                except Exception as exc:
                    logger.exception("Failed to refresh presence after AI restart: %s", exc)

        status = "available" if available else "unavailable"
        detail_msg = detail or "ready"
        console_print(f"AI engine restart complete: {status} ({detail_msg})")


async def handle_console_command(command: str, control: ConsoleControl) -> None:
    """Interpret and execute a single console command line.

    Parameters
    ----------
    command:
        Raw command string entered by the operator.
    control:
        Console management helper exposing the active bot and shutdown state.
    """
    cmd = command.strip().lower()
    if not cmd:
        return

    if cmd in {"quit", "exit", "shutdown"}:
        console_print("Shutdown requested.")
        control.request_shutdown()
        bot = control.bot
        if bot is not None and not bot.is_closed():
            try:
                await bot.close()
            except Exception as exc:
                logger.exception("Error while closing bot from console: %s", exc)
        return

    if cmd == "restart":
        await restart_ai_engine(control)
        return

    if cmd == "status":
        availability = "available" if model_state.available else "unavailable"
        detail = model_state.init_error or "ready"
        guilds = len(control.bot.guilds) if control.bot else 0
        console_print(f"Status: AI {availability}, ({detail}); connected guilds: {guilds}")
        return

    if cmd == "help":
        console_print("Commands: help, status, restart, shutdown")
        return

    console_print(f"Unknown command '{command}'. Type 'help' for options.", "ansired")


async def run_console(control: ConsoleControl) -> None:
    """Run the interactive developer console until shutdown is requested.

    Parameters
    ----------
    control:
        ConsoleControl coordinating shutdown events and bot access.
    """
    session = PromptSession("> ")  # <-- classic '>' prompt
    console_print("Interactive console ready. Type 'help' for commands.", "ansigreen")

    with patch_stdout():
        while not control.is_shutdown_requested():
            try:
                line = await session.prompt_async()  # prompt shows '>'
                if line.strip():
                    await handle_console_command(line, control)
            except (EOFError, KeyboardInterrupt):
                console_print("\nShutdown requested by user.")
                control.request_shutdown()
                break
            except Exception as exc:
                logger.exception("Error in console input loop: %s", exc)
                console_print(f"Error: {exc}", "ansired")


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
    from modcord.bot.cogs import debug_cmds, guild_settings_cmds, moderation_cmds
    debug_cmds.setup(discord_bot_instance)
    events_listener.setup(discord_bot_instance)
    guild_settings_cmds.setup(discord_bot_instance)
    moderation_cmds.setup(discord_bot_instance)
    logger.info("All cogs loaded successfully.")


async def initialize_ai_model() -> None:
    """Initialize the AI moderation engine prior to connecting the Discord client.

    Raises
    ------
    Exception
        Propagated when the underlying initializer encounters an unexpected failure.
    """
    try:
        logger.info("Initializing AI moderation engine before bot startup…")
        available, detail = await initialize_engine()
        if detail and not available:
            logger.critical("AI model failed to initialize: %s", detail)
    except Exception as exc:
        logger.critical("Unexpected error during AI initialization: %s", exc, exc_info=True)
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
        raise
    finally:
        logger.info("Discord bot start routine finished.")


async def shutdown_runtime(bot: discord.Bot | None = None) -> None:
    """Gracefully stop the Discord bot, AI engine, and guild settings manager.

    Parameters
    ----------
    bot:
        Optional bot instance to close before shutting down subsystems.
    """
    if bot is not None and not bot.is_closed():
        try:
            await bot.close()
            logger.info("Discord bot connection closed.")
        except Exception as exc:
            logger.exception("Error while closing Discord bot: %s", exc)

    try:
        await shutdown_engine()
    except Exception as exc:
        logger.exception("Error during moderation processor shutdown: %s", exc)

    try:
        await guild_settings_manager.shutdown()
    except Exception as exc:
        logger.exception("Error during guild settings shutdown: %s", exc)


async def async_main() -> int:
    """Bootstrap the bot, console, and AI engine, returning an exit code.

    Returns
    -------
    int
        Process exit code reflecting success or failure of initialization.
    """
    token = load_environment()
    bot = discord.Bot(intents=build_intents())
    load_cogs(bot)

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
    control.set_bot(bot)
    console_task: asyncio.Task[None] | None = None

    try:
        console_task = asyncio.create_task(run_console(control))
        exit_code = 0
        try:
            await start_bot(bot, token)
        except asyncio.CancelledError:
            logger.info("Bot start cancelled; proceeding to shutdown")
            exit_code = 0
        except Exception as exc:
            logger.critical("Discord bot runtime error: %s", exc, exc_info=True)
            exit_code = 1
        finally:
            control.stop()
            control.set_bot(None)
            if console_task:
                console_task.cancel()
                try:
                    await console_task
                except asyncio.CancelledError:
                    pass
            await shutdown_runtime(bot)

        return exit_code
    finally:
        control.stop()


def main() -> int:
    """Entrypoint that orchestrates the async runtime and returns the process code.

    Returns
    -------
    int
        Exit code propagated to the operating system.
    """
    logger.info("Starting Discord Moderation Bot…")
    try:
        return asyncio.run(async_main())
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
        logger.critical("An unexpected error occurred while running the bot: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.excepthook = handle_exception
    print(f"Exited with code: {main()}")
