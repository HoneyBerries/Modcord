"""
======================
Discord Moderation Bot
======================

A Discord bot that uses an AI model to moderate chat, handle rule violations,
and provide server administration commands for manual moderation actions like
banning, kicking, and timing out users.
"""

# =============================================================
# Standard library imports
# =============================================================
import os
import gc
import sys
import asyncio
from pathlib import Path

# =============================================================
# Path / environment bootstrap
# =============================================================

def resolve_base_dir() -> Path:
    """
    Resolve the Modcord project base directory.

    Resolution order:
    1. MODCORD_HOME environment variable
    2. Frozen/compiled executable location
    3. Project root inferred from source layout
    """
    if env_home := os.getenv("MODCORD_HOME"):
        return Path(env_home).resolve()

    if getattr(sys, "frozen", False) or getattr(sys, "compiled", False):
        return Path(sys.argv[0]).resolve().parent

    return Path(__file__).resolve().parents[2]

BASE_DIR = resolve_base_dir()
os.chdir(BASE_DIR)

# =============================================================
# Rest of the imports (safe after BASE_DIR is resolved)
# =============================================================
import discord
from dotenv import load_dotenv
from modcord.listener import events_listener, message_listener
from modcord.command import debug_cmds, guild_settings_cmds, moderation_cmds
from modcord.database import database as db
from modcord.settings import guild_settings_manager as gsm
from modcord.scheduler import (
    guidelines_sync_scheduler,
    rules_sync_scheduler,
    unban_scheduler,
)
from modcord.moderation import moderation_pipeline
from modcord.ui import console
from modcord.util.logger import get_logger, handle_exception

logger = get_logger("main")

# =============================================================
# Configuration helpers
# =============================================================

def load_environment() -> str:
    """Load environment variables and return the Discord bot token."""
    load_dotenv(dotenv_path=BASE_DIR / ".env")

    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        logger.critical("'DISCORD_BOT_TOKEN' environment variable not set.")
        sys.exit(1)

    return token


def build_intents() -> discord.Intents:
    """Construct Discord intents required by Modcord."""
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.messages = True
    intents.reactions = True
    intents.members = True
    return intents

# =============================================================
# Bot construction & wiring
# =============================================================

def load_cogs(bot: discord.Bot) -> None:
    """Attach all commands, listeners, and schedulers to the bot."""
    logger.info("[MAIN] Loading cogs…")

    # Commands
    debug_cmds.setup(bot)
    guild_settings_cmds.setup(bot)
    moderation_cmds.setup(bot)

    # Event listeners
    events_listener.setup(bot)
    message_listener.setup(bot)

    # Background schedulers
    rules_sync_scheduler.setup(bot)
    guidelines_sync_scheduler.setup(bot)
    unban_scheduler.setup(bot)

    logger.info("[MAIN] Cogs loaded successfully.")


def create_bot() -> discord.Bot:
    """Create and fully configure the Discord bot instance."""
    bot = discord.Bot(intents=build_intents())
    load_cogs(bot)
    return bot

# =============================================================
# Runtime lifecycle
# =============================================================

async def shutdown_runtime(bot: discord.Bot) -> None:
    """Gracefully shut down all Modcord subsystems."""
    try:
        await console.close_bot_instance(bot)
    except Exception as exc:
        logger.exception("Discord shutdown error: %s", exc)

    try:
        await moderation_pipeline.llm_engine.shutdown()
    except Exception as exc:
        logger.exception("LLM engine shutdown error: %s", exc)

    try:
        await gsm.guild_settings_manager.shutdown()
    except Exception as exc:
        logger.exception("Guild settings shutdown error: %s", exc)

    try:
        await db.database.shutdown()
    except Exception as exc:
        logger.exception("Database shutdown error: %s", exc)

    try:
        gc.collect()
    except Exception as exc:
        logger.exception("Garbage collection failed: %s", exc)

    logger.info("[MAIN] Shutdown complete.")


async def run_bot(bot: discord.Bot, token: str, control: console.ConsoleControl) -> int:
    """Run the Discord bot inside a managed console session."""
    logger.info("[MAIN] Starting Discord bot…")
    control.set_bot(bot)
    exit_code = 0

    async with console.console_session(control):
        try:
            await bot.start(token)
        except asyncio.CancelledError:
            logger.info("[MAIN] Bot startup cancelled.")
        except Exception as exc:
            logger.critical("Discord runtime error: %s", exc)
            exit_code = 200
        finally:
            await shutdown_runtime(bot)

    return exit_code

# =============================================================
# Application entrypoints
# =============================================================

async def async_main() -> int:
    """Async bootstrap and orchestration entrypoint."""
    token = load_environment()

    try:
        logger.info("[MAIN] Initializing database and guild settings…")
        await gsm.guild_settings_manager.async_init()
    except Exception as exc:
        logger.critical("Database initialization failed: %s", exc)
        return 500

    try:
        bot = create_bot()
    except Exception as exc:
        logger.critical("Bot initialization failed: %s", exc)
        return 400

    control = console.ConsoleControl(bot)
    exit_code = await run_bot(bot, token, control)

    if control.is_restart_requested():
        logger.info("[MAIN] Restart requested.")
        return -1

    return exit_code


def main() -> int:
    """Synchronous process entrypoint."""
    logger.info("[MAIN] Launching Modcord…")

    try:
        exit_code = asyncio.run(async_main())

        if exit_code == -1:
            logger.info("[MAIN] Replacing process for restart.")
            os.execv(sys.executable, [sys.executable] + sys.argv)
            return 0

        return exit_code

    except KeyboardInterrupt:
        logger.info("[MAIN] Shutdown requested by user.")
        return 0

    except SystemExit as exc:
        return int(exc.code) # type: ignore
    
    except Exception as exc:
        logger.critical("Unhandled fatal error: %s", exc)
        return 1


if __name__ == "__main__":
    sys.excepthook = handle_exception
    print(f"Exited with code: {main()}")