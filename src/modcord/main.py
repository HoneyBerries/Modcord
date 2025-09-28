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
from typing import Iterable
import asyncio
import discord
from dotenv import load_dotenv

from modcord.ai.ai_moderation_processor import model_state, moderation_processor
from modcord.bot.cogs import events_listener
from modcord.configuration.guild_settings import guild_settings_manager
from modcord.util.logger import get_logger, handle_exception


# Set the base directory to the project root
BASE_DIR = Path(__file__).resolve().parent.parent.parent

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


async def restart_ai_pipeline(control: ConsoleControl) -> None:
    """Restart the AI moderation pipeline without dropping the Discord connection."""

    async with control.restart_lock:
        print("[console] Restarting AI moderation pipeline…", flush=True)
        try:
            await moderation_processor.shutdown()
        except Exception as exc:  # noqa: BLE001 - log but continue to re-init
            logger.exception("Error while shutting down moderation processor: %s", exc)

        model_state.available = False
        model_state.init_error = None

        success = await moderation_processor.init_model()
        if success:
            await moderation_processor.start_batch_worker()

        bot = control.bot
        if bot is not None:
            events_cog = bot.get_cog("EventsListenerCog")
            updater = getattr(events_cog, "update_presence_for_model_state", None)
            if callable(updater):
                try:
                    maybe_coro = updater()
                    if asyncio.iscoroutine(maybe_coro):
                        await maybe_coro
                except Exception as exc:  # noqa: BLE001 - best-effort update
                    logger.exception("Failed to refresh presence after AI restart: %s", exc)

        status = "available" if model_state.available else "unavailable"
        detail = model_state.init_error or "ready"
        print(f"[console] AI pipeline restart complete: {status} ({detail}).", flush=True)


async def handle_console_command(command: str, control: ConsoleControl) -> None:
    cmd = command.strip().lower()
    if not cmd:
        return

    if cmd in {"quit", "exit", "shutdown"}:
        print("[console] Shutdown requested.", flush=True)
        control.request_shutdown()
        bot = control.bot
        if bot is not None and not bot.is_closed():
            try:
                await bot.close()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Error while closing bot from console: %s", exc)
        return

    if cmd == "restart":
        await restart_ai_pipeline(control)
        return

    if cmd == "status":
        availability = "available" if model_state.available else "unavailable"
        detail = model_state.init_error or "ready"
        guilds = len(control.bot.guilds) if control.bot else 0
        print(
            f"[Console] Status: AI {availability} ({detail}); connected guilds: {guilds}",
            flush=True,
        )
        return

    if cmd == "help":
        print(
            "[console] Commands: help, status, restart, shutdown",
            flush=True,
        )
        return

    print(f"[console] Unknown command '{command}'. Type 'help' for options.", flush=True)


async def run_console(control: ConsoleControl) -> None:
    """Run a simple stdin-based console for runtime control commands."""

    print("[console] Interactive console ready. Type 'help' for commands.", flush=True)
    try:
        while not control.is_shutdown_requested():
            try:
                # Print prompt and flush to ensure it appears before input
                print("> ", end="", flush=True)
                line = await asyncio.to_thread(sys.stdin.readline)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Console input error: %s", exc)
                break

            if line == "":
                await asyncio.sleep(0.25)
                continue

            await handle_console_command(line, control)
    except asyncio.CancelledError:
        logger.debug("Console loop cancelled")
        raise


def load_environment() -> str:
    """Load environment variables and return the Discord bot token."""
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


def discover_cog_modules() -> Iterable[str]:
    return (
        "modcord.bot.cogs.debug_cmds",
        "modcord.bot.cogs.events",
        "modcord.bot.cogs.guild_settings_cmds",
        "modcord.bot.cogs.moderation_cmds",
    )


def load_cogs(discord_bot_instance: discord.Bot) -> None:
    """Load cogs by importing modules explicitly from the cogs package."""
    from modcord.bot.cogs import debug_cmds, guild_settings_cmds, moderation_cmds

    debug_cmds.setup(discord_bot_instance)
    events_listener.setup(discord_bot_instance)
    guild_settings_cmds.setup(discord_bot_instance)
    moderation_cmds.setup(discord_bot_instance)
    logger.info("All cogs loaded successfully.")

async def initialize_ai_model() -> None:
    try:
        logger.info("Initializing AI model before bot startup…")
        await moderation_processor.init_model()
        await moderation_processor.start_batch_worker()
        if model_state.init_error and not model_state.available:
            logger.critical("AI model failed to initialize: %s", model_state.init_error)
    except Exception as exc:  # noqa: BLE001 - surface initialization failures
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
    """Gracefully shut down background services and Discord client."""

    if bot is not None and not bot.is_closed():
        try:
            await bot.close()
            logger.info("Discord bot connection closed.")
        except Exception as exc:  # noqa: BLE001 - best-effort shutdown
            logger.exception("Error while closing Discord bot: %s", exc)

    try:
        await moderation_processor.shutdown()
    except Exception as exc:  # noqa: BLE001 - log and continue shutdown
        logger.exception("Error during moderation processor shutdown: %s", exc)

    try:
        await guild_settings_manager.shutdown()
    except Exception as exc:  # noqa: BLE001 - log and continue shutdown
        logger.exception("Error during guild settings shutdown: %s", exc)


async def async_main() -> int:
    token = load_environment()
    if not token:
        return 1

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
        except Exception as exc:  # noqa: BLE001 - bubble unexpected runtime errors
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
        # Ensure console is stopped if initialization failed before entering the inner try/finally.
        control.stop()


def main() -> int:
    """Synchronous entrypoint that delegates to the async runner."""
    logger.info("Starting Discord Moderation Bot…")
    try:
        return asyncio.run(async_main())
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user.")
        return 0
    except SystemExit as exit_exc:
        # SystemExit.code may be an int, str, or None — normalize to int for the function return type.
        code = exit_exc.code
        if isinstance(code, int):
            return code
        if code is None:
            return 0
        try:
            return int(code)
        except (ValueError, TypeError):
            logger.warning("SystemExit.code is not an int (%r); defaulting to 1", code)
            return 1
    except Exception as exc:
        logger.critical("An unexpected error occurred while running the bot: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    # Set the global exception hook to use the custom handler
    sys.excepthook = handle_exception
    print("Exited with code:", main())
