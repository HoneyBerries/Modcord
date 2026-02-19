"""Interactive console utilities for managing the live Discord bot."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

import discord
from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.shortcuts import PromptSession

from modcord.util.logger import get_logger

# Box drawing helpers for aligned console output
BOX_WIDTH = 60

def print_boxed_title(title: str, color: str = "") -> None:
    """
    Print a centered title inside a box drawn with Unicode box-drawing characters.
    
    The box has a fixed width defined by BOX_WIDTH and the title is centered
    within it. The box is drawn using ╔═══╗ style characters.
    
    Args:
        title (str): The text to display in the center of the box.
        color (str): Optional ANSI color code to apply to the entire box.
    """
    inner_width = BOX_WIDTH - 2
    pad_left = (inner_width - len(title)) // 2
    pad_right = inner_width - len(title) - pad_left
    top = f"╔{'═' * inner_width}╗"
    mid = f"║{' ' * pad_left}{title}{' ' * pad_right}║"
    bot = f"╚{'═' * inner_width}╝"
    for line in (top, mid, bot):
        console_print(line, color)

logger = get_logger("console")

# Type alias for console handler functions
CommandHandler = Callable[["ConsoleControl", list[str]], Awaitable[None]]


@dataclass
class Command:
    """
    Definition of a console console with handler and metadata.
    
    This dataclass encapsulates all information needed to register and execute
    a console console, including its name, aliases, handler function, and help text.
    
    Attributes:
        name (str): Primary name of the console.
        handler (CommandHandler): Async function to execute when console is invoked.
        aliases (list[str]): Alternative names that can trigger this console.
        description (str): Human-readable description shown in help text.
        usage (str): Optional usage string showing console syntax.
    """
    name: str
    handler: CommandHandler
    aliases: list[str]
    description: str
    usage: str = ""

    def matches(self, input_cmd: str) -> bool:
        """Check if input matches this console or any alias."""
        return input_cmd == self.name or input_cmd in self.aliases


def console_print(message: str, style: str = "") -> None:
    """
    Print text to the console using prompt_toolkit without breaking active prompts.
    
    This function uses prompt_toolkit's print_formatted_text to ensure console
    output doesn't interfere with the user's current input line.
    
    Args:
        message (str): The text to print to the console.
        style (str): Optional ANSI style code to apply to the message.
    """
    formatted: FormattedText | str
    if style:
        formatted = FormattedText([(style, message)])
    else:
        formatted = message
    print_formatted_text(formatted)


class ConsoleControl:
    """
    Manager for console-driven bot lifecycle controls.
    
    This class coordinates shutdown and restart requests from the interactive console,
    maintaining state flags and providing access to the Discord bot instance.
    
    Attributes:
        shutdown_event (asyncio.Event): Event that signals shutdown request.
        restart_event (asyncio.Event): Event that signals restart request.
    
    Methods:
        set_bot: Set the Discord bot instance reference.
        request_shutdown: Signal that the bot should shut down.
        request_restart: Signal that the bot should restart.
        stop: Alias for request_shutdown.
        is_shutdown_requested: Check if shutdown has been requested.
        is_restart_requested: Check if restart has been requested.
    """

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
    """
    Gracefully close the Discord bot connection if active.
    
    Sets the bot's status to offline before closing to indicate proper shutdown.
    All exceptions during closure are caught and logged to prevent crashes during
    shutdown.
    
    Args:
        bot (discord.Bot | None): The Discord bot instance to close. If None or
            already closed, this function does nothing.
        log_close (bool): Whether to log a confirmation message after closing.
            Defaults to False.
    """
    if bot is None or bot.is_closed():
        return

    try:
        # Set bot status to offline before closing
        await bot.change_presence(status=discord.Status.offline)
        await bot.close()
        if log_close:
            logger.info("[CONSOLE] Discord bot connection closed.")
    except Exception as exc:
        logger.exception("Error while closing Discord bot: %s", exc)


async def _request_lifecycle_action(control: ConsoleControl, *, restart: bool) -> None:
    """
    Internal helper to trigger shutdown or restart from console commands.
    
    Sets the appropriate event flags and closes the bot connection gracefully.
    
    Args:
        control (ConsoleControl): The control object managing lifecycle state.
        restart (bool): If True, sets restart flag; otherwise only sets shutdown flag.
    """
    if restart:
        control.request_restart()
    control.request_shutdown()
    await close_bot_instance(control.bot)


# ==================== Command Handlers ====================

async def cmd_help(control: ConsoleControl, args: list[str]) -> None:
    """
    Display available commands and their descriptions.
    
    Prints a formatted reference of all registered console commands including
    their names, aliases, descriptions, and usage information.
    
    Args:
        control (ConsoleControl): The console control instance.
        args (list[str]): Command arguments (unused for this console).
    """
    print_boxed_title("Console Commands Reference", "ansigreen")
    for cmd in COMMANDS:
        aliases_str = f" (aliases: {', '.join(cmd.aliases)})" if cmd.aliases else ""
        console_print(f"\n  {cmd.name}{aliases_str}", "ansicyan")
        console_print(f"    {cmd.description}")
        if cmd.usage:
            console_print(f"    Usage: {cmd.usage}", "ansibrightblack")
    console_print("")


async def cmd_status(control: ConsoleControl, args: list[str]) -> None:
    """
    Display comprehensive bot and AI engine status information.
    
    Shows the current state of:
    - AI moderation engine (available/unavailable)
    - Bot connection status
    - Number of connected guilds
    - Current latency
    
    Args:
        control (ConsoleControl): The console control instance.
        args (list[str]): Command arguments (unused for this console).
    """

    print_boxed_title("Bot Status", "ansimagenta")

    # AI Status (OpenAI API mode - always ready, failures handled per-request)
    console_print("  AI Engine:  🟢 Ready (OpenAI API mode)")
    
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
    """
    List all guilds (servers) the bot is currently connected to.
    
    Displays each guild's name, ID, and member count in a formatted list.
    
    Args:
        control (ConsoleControl): The console control instance.
        args (list[str]): Command arguments (unused for this console).
    """
    if not control.bot or not control.bot.guilds:
        console_print("No guilds found or bot not connected.", "ansiyellow")
        return
    

    title = f"Connected Guilds ({len(control.bot.guilds)})"
    print_boxed_title(title, "ansiblue")
    
    for guild in control.bot.guilds:
        console_print(f"  • {guild.name} (ID: {guild.id}, Members: {guild.member_count})")
    
    console_print("")


async def cmd_clear(control: ConsoleControl, args: list[str]) -> None:
    """
    Clear the console screen.
    
    Uses platform-appropriate commands ('cls' on Windows, 'clear' on Unix-like systems)
    to clear the terminal screen.
    
    Args:
        control (ConsoleControl): The console control instance.
        args (list[str]): Command arguments (unused for this console).
    """
    os.system('cls' if os.name == 'nt' else 'clear')
    console_print("Console cleared.", "ansibrightcyan")


async def cmd_restart(control: ConsoleControl, args: list[str]) -> None:
    """
    Request a full bot restart.
    
    Triggers both restart and shutdown flags, causing the bot to shut down cleanly
    and then restart with a fresh process. The main loop will detect the restart
    flag and handle process replacement.
    
    Args:
        control (ConsoleControl): The console control instance.
        args (list[str]): Command arguments (unused for this console).
    """
    console_print("Restart requested. Bot will shut down and restart...", "ansiyellow")
    await _request_lifecycle_action(control, restart=True)


async def cmd_shutdown(control: ConsoleControl, args: list[str]) -> None:
    """
    Request graceful bot shutdown.
    
    Triggers the shutdown flag, causing the bot to close all connections, clean up
    resources, and exit the process gracefully.
    
    Args:
        control (ConsoleControl): The console control instance.
        args (list[str]): Command arguments (unused for this console).
    """
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
    """
    Parse and execute a console console line.
    
    Splits the input into console name and arguments, finds the matching console
    in the registry, and executes its handler. If no matching console is found,
    displays an error message.
    
    Args:
        command (str): The raw console line input from the user.
        control (ConsoleControl): The console control instance to pass to handlers.
    """
    if not command.strip():
        return
    
    parts = command.strip().split()
    cmd_name = parts[0].lower()
    args = parts[1:]
    
    # Find matching console
    for cmd in COMMANDS:
        if cmd.matches(cmd_name):
            try:
                await cmd.handler(control, args)
            except Exception as exc:
                logger.exception("Error executing console '%s': %s", cmd_name, exc)
                console_print(f"Error executing console: {exc}", "ansibrightred")
            return
    
    # No console found
    console_print(f"Unknown console '{cmd_name}'. Type 'help' for available commands.", "ansibrightred")

async def run_console(control: ConsoleControl) -> None:
    """
    Run the interactive developer console until shutdown is requested.
    
    Creates a prompt_toolkit session and continuously reads user input, dispatching
    commands until the shutdown event is triggered via console or keyboard interrupt.
    
    Args:
        control (ConsoleControl): The console control instance managing lifecycle.
    """
    session = PromptSession("> ")
    
    # Welcome message
    print_boxed_title("Modcord Interactive Console", "ansicyan")
    console_print("Type 'help' for available commands or 'exit' to quit.\n", "ansibrightblack")

    with patch_stdout():
        while not control.is_shutdown_requested():
            try:
                line = await session.prompt_async()
                if line.strip():
                    await handle_console_command(line, control)
            except (EOFError, KeyboardInterrupt):
                console_print("\nShutdown requested by user.", "ansibrightyellow")
                control.request_shutdown()
                break
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception("Error in console input loop: %s", exc)
                console_print(f"Error: {exc}", "ansibrightred")


@asynccontextmanager
async def console_session(control: ConsoleControl) -> AsyncIterator[ConsoleControl]:
    """
    Context manager that runs the console alongside the bot with automatic cleanup.
    
    Starts the console in a background task and ensures it's properly cancelled
    and cleaned up when the context exits, regardless of how the exit occurs.
    
    Args:
        control (ConsoleControl): The console control instance to run.
    
    Yields:
        ConsoleControl: The control instance for use within the context.
    
    Example:
        async with console_session(control):
            await bot.start(token)
    """
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
