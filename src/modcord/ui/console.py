"""Interactive console utilities for managing the live Discord bot."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
import os

import discord
from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.shortcuts import PromptSession


from modcord.ai.ai_moderation_processor import model_state
from modcord.util.logger import get_logger

# Box drawing helpers for aligned console output
BOX_WIDTH = 45

def box_line(char: str) -> str:
    return char * BOX_WIDTH

def box_title(title: str) -> list[str]:
    inner_width = BOX_WIDTH - 2
    pad_left = (inner_width - len(title)) // 2
    pad_right = inner_width - len(title) - pad_left
    return [
        f"╔{'═' * inner_width}╗",
        f"║{' ' * pad_left}{title}{' ' * pad_right}║",
        f"╚{'═' * inner_width}╝"
    ]

logger = get_logger("console")

# Type alias for command handler functions
CommandHandler = Callable[["ConsoleControl", list[str]], Awaitable[None]]


@dataclass
class Command:
    """Definition of a console command."""
    name: str
    handler: CommandHandler
    aliases: list[str]
    description: str
    usage: str = ""

    def matches(self, input_cmd: str) -> bool:
        """Check if input matches this command or any alias."""
        return input_cmd == self.name or input_cmd in self.aliases


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


# ==================== Command Handlers ====================

async def cmd_help(control: ConsoleControl, args: list[str]) -> None:
    """Display available commands and their descriptions."""
    console_print("\n╔═══════════════════════════════════════════╗", "ansigreen")
    console_print("║       Console Commands Reference          ║", "ansigreen")
    console_print("╚═══════════════════════════════════════════╝", "ansigreen")
    
    for cmd in COMMANDS:
        aliases_str = f" (aliases: {', '.join(cmd.aliases)})" if cmd.aliases else ""
        console_print(f"\n  {cmd.name}{aliases_str}", "ansicyan")
        console_print(f"    {cmd.description}")
        if cmd.usage:
            console_print(f"    Usage: {cmd.usage}", "ansibrightblack")
    
    console_print("")


async def cmd_status(control: ConsoleControl, args: list[str]) -> None:
    """Display bot and AI status information."""

    for line in box_title("Bot Status"):
        console_print(line, "ansiblue")

    # AI Status
    ai_status = "🟢 Available" if model_state.available else "🔴 Unavailable"
    ai_detail = model_state.init_error or "ready"
    console_print(f"  AI Engine:  {ai_status} ({ai_detail})")
    
    # Bot connection status
    if control.bot:
        bot_status = "🟢 Connected" if not control.bot.is_closed() else "🔴 Disconnected"
        guilds = len(control.bot.guilds)
        console_print(f"  Bot:        {bot_status}")
        console_print(f"  Guilds:     {guilds}")
        console_print(f"  Latency:    {control.bot.latency * 1000:.0f}ms")
    else:
        console_print("  Bot:        🔴 Not initialized")
    
    console_print("")


async def cmd_guilds(control: ConsoleControl, args: list[str]) -> None:
    """List all guilds the bot is connected to."""
    if not control.bot or not control.bot.guilds:
        console_print("No guilds found or bot not connected.", "ansiyellow")
        return
    

    title = f"Connected Guilds ({len(control.bot.guilds)})"
    for line in box_title(title):
        console_print(line, "ansiblue")
    
    for guild in control.bot.guilds:
        console_print(f"  • {guild.name} (ID: {guild.id}, Members: {guild.member_count})")
    
    console_print("")


async def cmd_clear(control: ConsoleControl, args: list[str]) -> None:
    """Clear the console screen."""
    # ANSI escape code to clear screen and move cursor to home
    os.system('cls' if os.name == 'nt' else 'clear')
    console_print("Console cleared.", "ansigreen")


async def cmd_restart(control: ConsoleControl, args: list[str]) -> None:
    """Request a full bot restart."""
    console_print("Restart requested. Bot will shut down and restart...", "ansiyellow")
    await _request_lifecycle_action(control, restart=True)


async def cmd_shutdown(control: ConsoleControl, args: list[str]) -> None:
    """Request graceful bot shutdown."""
    console_print("Shutdown requested.", "ansiyellow")
    await _request_lifecycle_action(control, restart=False)


# ==================== Command Registry ====================

COMMANDS: list[Command] = [
    Command(
        name="help",
        handler=cmd_help,
        aliases=["h", "?"],
        description="Show this help message with all available commands",
    ),
    Command(
        name="status",
        handler=cmd_status,
        aliases=["stat", "info"],
        description="Display bot status, AI engine status, and connection info",
    ),
    Command(
        name="guilds",
        handler=cmd_guilds,
        aliases=["servers", "g"],
        description="List all guilds (servers) the bot is connected to",
    ),
    Command(
        name="clear",
        handler=cmd_clear,
        aliases=["cls"],
        description="Clear the console screen",
    ),
    Command(
        name="restart",
        handler=cmd_restart,
        aliases=["reboot"],
        description="Fully restart the entire bot (useful during development)",
    ),
    Command(
        name="shutdown",
        handler=cmd_shutdown,
        aliases=["stop", "quit", "exit"],
        description="Gracefully shut down the bot",
    ),
]


# ==================== Command Dispatcher ====================

async def handle_console_command(command: str, control: ConsoleControl) -> None:
    """Interpret and execute a single console command line."""
    if not command.strip():
        return
    
    parts = command.strip().split()
    cmd_name = parts[0].lower()
    args = parts[1:]
    
    # Find matching command
    for cmd in COMMANDS:
        if cmd.matches(cmd_name):
            try:
                await cmd.handler(control, args)
            except Exception as exc:
                logger.exception("Error executing command '%s': %s", cmd_name, exc)
                console_print(f"Error executing command: {exc}", "ansired")
            return
    
    # No command found
    console_print(f"Unknown command '{cmd_name}'. Type 'help' for available commands.", "ansired")


async def run_console(control: ConsoleControl) -> None:
    """Run the interactive developer console until shutdown is requested."""
    session = PromptSession("> ")
    
    # Welcome message
    console_print("\n╔═════════════════════════════════════╗", "ansigreen")
    console_print(  "║     Modcord Interactive Console     ║", "ansigreen")
    console_print(  "╚═════════════════════════════════════╝", "ansigreen")
    console_print("Type 'help' for available commands or 'exit' to quit.\n", "ansibrightblack")

    with patch_stdout():
        while not control.is_shutdown_requested():
            try:
                line = await session.prompt_async()
                if line.strip():
                    await handle_console_command(line, control)
            except (EOFError, KeyboardInterrupt):
                console_print("\nShutdown requested by user.", "ansiyellow")
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
