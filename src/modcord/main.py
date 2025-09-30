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
        return Path(sys.argv[0]).resolve().parent  # works for Nuitka/PyInstaller

    return Path(__file__).resolve().parents[2]

BASE_DIR = resolve_base_dir()
os.chdir(BASE_DIR)

import asyncio
import discord
from dotenv import load_dotenv
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.shortcuts import PromptSession
from rich.console import Console

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


# Global rich console
console = Console()

# Get logger for this module
logger = get_logger("main")


class ConsoleControl:
    """Coordinate console commands with the running bot instance."""

    def __init__(self) -> None:
        self.shutdown_event = asyncio.Event()
        self.restart_lock = asyncio.Lock()
        self._bot: discord.Bot | None = None

    def set_bot(self, bot: discord.Bot | None) -> None:
        self._bot = bot

    @property
    def bot(self) -> discord.Bot | None:
        return self._bot

    def request_shutdown(self) -> None:
        self.shutdown_event.set()

    def stop(self) -> None:
        self.shutdown_event.set()

    def is_shutdown_requested(self) -> bool:
        return self.shutdown_event.is_set()


async def restart_ai_engine(control: ConsoleControl) -> None:
    """Restart the AI moderation engine without dropping the Discord connection."""
    async with control.restart_lock:
        console.print("Restarting AI moderation engine…")
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
        console.print(f"AI engine restart complete: {status} ({detail_msg})")


async def handle_console_command(command: str, control: ConsoleControl) -> None:
    cmd = command.strip().lower()
    if not cmd:
        return

    if cmd in {"quit", "exit", "shutdown"}:
        console.print("Shutdown requested.")
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
        console.print(f"Status: AI {availability}, ({detail}); connected guilds: {guilds}")
        return

    if cmd == "help":
        console.print("Commands: help, status, restart, shutdown")
        return

    console.print(f"Unknown command '{command}'. Type 'help' for options.")


async def run_console(control: ConsoleControl) -> None:
    """
    Async console using prompt_toolkit + rich.
    Handles user commands with a classic '>' prompt.
    """
    session = PromptSession("> ")  # <-- classic '>' prompt
    console.print("Interactive console ready. Type 'help' for commands.")

    with patch_stdout():
        while not control.is_shutdown_requested():
            try:
                line = await session.prompt_async()  # prompt shows '>'
                if line.strip():
                    await handle_console_command(line, control)
            except (EOFError, KeyboardInterrupt):
                console.print("\nShutdown requested by user.")
                control.request_shutdown()
                break
            except Exception as exc:
                logger.exception("Error in console input loop: %s", exc)
                console.print(f"Error: {exc}")



def load_environment() -> str:
    load_dotenv(dotenv_path=BASE_DIR / ".env")
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        logger.critical("'DISCORD_BOT_TOKEN' environment variable not set. Bot cannot start.")
        sys.exit(1)
    return token


def build_intents() -> discord.Intents:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.messages = True
    intents.reactions = True
    intents.members = True
    return intents


def load_cogs(discord_bot_instance: discord.Bot) -> None:
    from modcord.bot.cogs import debug_cmds, guild_settings_cmds, moderation_cmds
    debug_cmds.setup(discord_bot_instance)
    events_listener.setup(discord_bot_instance)
    guild_settings_cmds.setup(discord_bot_instance)
    moderation_cmds.setup(discord_bot_instance)
    logger.info("All cogs loaded successfully.")


async def initialize_ai_model() -> None:
    try:
        logger.info("Initializing AI moderation engine before bot startup…")
        available, detail = await initialize_engine()
        if detail and not available:
            logger.critical("AI model failed to initialize: %s", detail)
    except Exception as exc:
        logger.critical("Unexpected error during AI initialization: %s", exc, exc_info=True)
        raise


async def start_bot(bot: discord.Bot, token: str) -> None:
    logger.info("Attempting to connect to Discord…")
    try:
        await bot.start(token)
    except asyncio.CancelledError:
        logger.info("Discord bot start cancelled; shutting down")
        raise
    finally:
        logger.info("Discord bot start routine finished.")


async def shutdown_runtime(bot: discord.Bot | None = None) -> None:
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
