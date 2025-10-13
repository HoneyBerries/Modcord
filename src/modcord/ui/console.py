"""Interactive console utilities for managing the live Discord bot."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import discord
from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.shortcuts import PromptSession

from modcord.ai.ai_moderation_processor import model_state
from modcord.util.logger import get_logger

logger = get_logger("console")


def console_print(message: str, style: str = "") -> None:
    """Render text via prompt_toolkit without breaking the active prompt."""
    formatted: FormattedText | str
    if style:
        formatted = FormattedText([(style, message)])
    else:
        formatted = message
    print_formatted_text(formatted)


class ConsoleControl:
    """Manage console-driven lifecycle controls for the running Discord bot."""

    def __init__(self) -> None:
        self.shutdown_event = asyncio.Event()
        self.restart_event = asyncio.Event()
        self._bot: discord.Bot | None = None

    def set_bot(self, bot: discord.Bot | None) -> None:
        self._bot = bot

    @property
    def bot(self) -> discord.Bot | None:  # pragma: no cover - trivial getter
        return self._bot

    def request_shutdown(self) -> None:
        self.shutdown_event.set()

    def request_restart(self) -> None:
        self.restart_event.set()

    def stop(self) -> None:
        self.shutdown_event.set()

    def is_shutdown_requested(self) -> bool:
        return self.shutdown_event.is_set()

    def is_restart_requested(self) -> bool:
        return self.restart_event.is_set()


async def close_bot_instance(bot: discord.Bot | None, *, log_close: bool = False) -> None:
    """Close the Discord bot instance if it is active."""
    if bot is None or bot.is_closed():
        return

    try:
        await bot.close()
        if log_close:
            logger.info("Discord bot connection closed.")
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Error while closing Discord bot: %s", exc)


async def _request_lifecycle_action(control: ConsoleControl, *, restart: bool) -> None:
    """Trigger shutdown or restart from the console, closing the bot safely."""
    if restart:
        control.request_restart()
    control.request_shutdown()
    await close_bot_instance(control.bot)


async def handle_console_command(command: str, control: ConsoleControl) -> None:
    """Interpret and execute a single console command line."""
    cmd = command.strip().lower()
    if not cmd:
        return

    if cmd in {"quit", "exit", "shutdown"}:
        console_print("Shutdown requested.")
        await _request_lifecycle_action(control, restart=False)
        return

    if cmd == "restart":
        console_print("Full restart requested. Bot will shut down and restart...")
        await _request_lifecycle_action(control, restart=True)
        return

    if cmd == "status":
        availability = "available" if model_state.available else "unavailable"
        detail = model_state.init_error or "ready"
        guilds = len(control.bot.guilds) if control.bot else 0
        console_print(f"Status: AI {availability}, ({detail}); connected guilds: {guilds}")
        return

    if cmd == "help":
        console_print("Available commands:", "ansigreen")
        console_print("  help     - Show this help message")
        console_print("  status   - Display bot and AI status")
        console_print("  restart  - Fully restart the entire bot (useful during development)")
        console_print("  shutdown - Gracefully shut down the bot")
        return

    console_print(f"Unknown command '{command}'. Type 'help' for options.", "ansired")


async def run_console(control: ConsoleControl) -> None:
    """Run the interactive developer console until shutdown is requested."""
    session = PromptSession("> ")
    console_print("Interactive console ready. Type 'help' for commands.", "ansigreen")

    with patch_stdout():
        while not control.is_shutdown_requested():
            try:
                line = await session.prompt_async()
                if line.strip():
                    await handle_console_command(line, control)
            except (EOFError, KeyboardInterrupt):
                console_print("\nShutdown requested by user.")
                control.request_shutdown()
                break
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception("Error in console input loop: %s", exc)
                console_print(f"Error: {exc}", "ansired")


@asynccontextmanager
async def console_session(control: ConsoleControl) -> AsyncIterator[ConsoleControl]:
    """Run the console alongside the bot, cleaning up automatically."""
    console_task = asyncio.create_task(run_console(control))
    try:
        yield control
    finally:
        control.stop()
        console_task.cancel()
        try:
            await console_task
        except asyncio.CancelledError:
            pass
