import os
import subprocess
import sys
import asyncio
import threading

# ===========================
# Bot Controller
# ===========================
# This script provides an interactive console to manage the lifecycle of a Discord bot.
# You can start, stop, reload, and check the status of the bot from the terminal.

BOT_PATH = "bot.py"  # Path to the bot script
proc = None          # Global reference to the bot process

# ANSI color codes for readability
COLOR_HEADER = "\033[95m"
COLOR_CMD = "\033[94m"
COLOR_DESC = "\033[92m"
COLOR_SUCCESS = "\033[92m"
COLOR_WARNING = "\033[93m"
COLOR_ERROR = "\033[91m"
COLOR_INFO = "\033[96m"
COLOR_RESET = "\033[0m"

def print_help():
    """
    Prints a descriptive, colorized help message for all available commands.
    """
    print(f"\n{COLOR_HEADER}╭─ Modcord Bot Supervisor Help ──╮{COLOR_RESET}")
    print(f"{COLOR_DESC}│ Manage your Discord bot from   │{COLOR_RESET}")
    print(f"{COLOR_DESC}│ this interactive console.      │{COLOR_RESET}")
    print(f"{COLOR_HEADER}╰────────────────────────────────╯{COLOR_RESET}\n")
    
    commands = [
        ("start", "Launch the bot if not already running"),
        ("stop", "Gracefully stop the running bot"),
        ("kill", "Force terminate the bot process"),
        ("reload", "Restart the bot (stop + start)"),
        ("status", "Check if the bot is running"),
        ("logs", "Show recent bot output (if available)"),
        ("clear", "Clear the console screen"),
        ("help/?", "Show this help message"),
        ("exit/quit", "Exit the supervisor"),
        ("hi/hello", "Friendly greeting")
    ]
    
    for cmd, desc in commands:
        print(f"  {COLOR_CMD}{cmd:<12}{COLOR_RESET} {COLOR_DESC}{desc}{COLOR_RESET}")
    
    print(f"\n{COLOR_INFO}💡 Commands are case-insensitive. Type and press Enter.{COLOR_RESET}\n")

def run_bot():
    """
    Launches the bot by starting a subprocess running the bot script.
    """
    global proc
    try:
        if not os.path.exists(BOT_PATH):
            print(f"{COLOR_ERROR}❌ Error: {BOT_PATH} not found!{COLOR_RESET}")
            return False
        
        proc = subprocess.Popen(
            [sys.executable, BOT_PATH],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        print(f"{COLOR_SUCCESS}✅ Bot started successfully (PID: {proc.pid}){COLOR_RESET}")
        return True
    except Exception as e:
        print(f"{COLOR_ERROR}❌ Failed to start bot: {e}{COLOR_RESET}")
        return False

def stop_bot(force=False):
    """
    Stops the bot process gracefully or forcefully.
    """
    global proc
    if not proc:
        print(f"{COLOR_WARNING}⚠️ No bot process to stop.{COLOR_RESET}")
        return
    
    if proc.poll() is not None:
        print(f"{COLOR_WARNING}⚠️ Bot is already stopped.{COLOR_RESET}")
        proc = None
        return
    
    try:
        if force:
            proc.kill()
            print(f"{COLOR_WARNING}🔪 Bot process killed forcefully.{COLOR_RESET}")
        else:
            proc.terminate()
            proc.wait(timeout=5)
            print(f"{COLOR_SUCCESS}✅ Bot stopped gracefully.{COLOR_RESET}")
    except subprocess.TimeoutExpired:
        print(f"{COLOR_WARNING}⚠️ Bot didn't stop gracefully, killing...{COLOR_RESET}")
        proc.kill()
    except Exception as e:
        print(f"{COLOR_ERROR}❌ Error stopping bot: {e}{COLOR_RESET}")
    finally:
        proc = None

def get_bot_status():
    """
    Returns the current status of the bot process.
    """
    if not proc:
        return "stopped", "No bot process"
    
    if proc.poll() is None:
        return "running", f"PID: {proc.pid}"
    else:
        return "stopped", f"Exit code: {proc.returncode}"

def clear_screen():
    """
    Clears the console screen.
    """
    os.system('cls' if os.name == 'nt' else 'clear')

async def console_loop():
    """
    Interactive console loop for managing the bot process.
    Enhanced with better error handling and more commands.
    """
    global proc
    
    while True:
        try:
            # Use asyncio.to_thread for non-blocking input
            cmd = (await asyncio.to_thread(input, f"{COLOR_CMD}> {COLOR_RESET}")).strip().lower()
            
            if not cmd:
                continue
                
            match cmd:
                case "start":
                    status, _ = get_bot_status()
                    if status == "running":
                        print(f"{COLOR_WARNING}⚠️ Bot is already running.{COLOR_RESET}")
                    else:
                        print(f"{COLOR_INFO}🚀 Starting bot...{COLOR_RESET}")
                        threading.Thread(target=run_bot, daemon=True).start()
                        
                case "stop":
                    print(f"{COLOR_INFO}🛑 Stopping bot...{COLOR_RESET}")
                    stop_bot(force=False)
                    
                case "kill":
                    print(f"{COLOR_WARNING}🔪 Force killing bot...{COLOR_RESET}")
                    stop_bot(force=True)
                    
                case "reload" | "restart":
                    print(f"{COLOR_INFO}🔄 Reloading bot...{COLOR_RESET}")
                    stop_bot(force=False)
                    await asyncio.sleep(1)  # Brief pause
                    threading.Thread(target=run_bot, daemon=True).start()
                    
                case "status":
                    status, details = get_bot_status()
                    if status == "running":
                        print(f"{COLOR_SUCCESS}✅ Bot is running ({details}){COLOR_RESET}")
                    else:
                        print(f"{COLOR_ERROR}❌ Bot is stopped ({details}){COLOR_RESET}")
                        
                case "logs":
                    print(f"{COLOR_INFO}📋 Log viewing not implemented yet.{COLOR_RESET}")
                    
                case "clear" | "cls":
                    clear_screen()
                    print(f"{COLOR_HEADER}Modcord Bot Supervisor - Type 'help' for commands{COLOR_RESET}")
                    
                case "hi" | "hello":
                    print(f"{COLOR_SUCCESS}👋 Hello there! Bot supervisor at your service.{COLOR_RESET}")
                    
                case "help" | "?":
                    print_help()
                    
                case "exit" | "quit":
                    print(f"{COLOR_INFO}👋 Shutting down supervisor...{COLOR_RESET}")
                    if proc and proc.poll() is None:
                        print(f"{COLOR_WARNING}🛑 Stopping bot before exit...{COLOR_RESET}")
                        stop_bot(force=False)
                    break
                    
                case _:
                    print(f"{COLOR_ERROR}❌ Unknown command: '{cmd}'. Type 'help' for available commands.{COLOR_RESET}")
                    
        except KeyboardInterrupt:
            print(f"\n{COLOR_WARNING}🛑 Ctrl+C detected. Use 'exit' to quit gracefully.{COLOR_RESET}")
        except Exception as e:
            print(f"{COLOR_ERROR}❌ Unexpected error: {e}{COLOR_RESET}")

async def main():
    """
    Main entry point with enhanced startup message.
    """
    clear_screen()
    print(f"{COLOR_HEADER}╭──────────────────────────────────╮{COLOR_RESET}")
    print(f"{COLOR_HEADER}│     HoneyBerries Supervisor      │{COLOR_RESET}")
    print(f"{COLOR_HEADER}│        Type 'help' for           │{COLOR_RESET}")
    print(f"{COLOR_HEADER}│        commands list             │{COLOR_RESET}")
    print(f"{COLOR_HEADER}╰──────────────────────────────────╯{COLOR_RESET}")
    print(f"{COLOR_INFO}📁 Bot script: {BOT_PATH}{COLOR_RESET}")
    print(f"{COLOR_DESC}Ready to manage multiple bots! 🤖{COLOR_RESET}\n")

    await console_loop()
    print(f"{COLOR_SUCCESS}✅ Supervisor shutdown complete.{COLOR_RESET}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{COLOR_WARNING}🛑 Supervisor interrupted.{COLOR_RESET}")
    except Exception as e:
        print(f"{COLOR_ERROR}❌ Fatal error: {e}{COLOR_RESET}")
        sys.exit(1)