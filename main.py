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

def run_bot():
    """
    Launches the bot by starting a subprocess running the bot script.
    """
    global proc
    proc = subprocess.Popen([sys.executable, BOT_PATH])


async def console_loop():
    """
    Interactive console loop for managing the bot process.
    Supports commands: start, stop, reload, status, help, hi/hello.
    """
    global proc
    while True:
        # Use asyncio.to_thread for non-blocking input
        cmd = await asyncio.to_thread(input, "> ")
        match cmd:
            case "stop":
                print("Stopping bot...")
                if proc:
                    proc.terminate()
                    proc.wait()
            case "reload":
                print("Reloading bot...")
                if proc:
                    proc.terminate()
                    proc.wait()
                run_bot()
            case "status":
                print("Bot is running..." if proc and proc.poll() is None else "Bot is stopped.")
            case "hi" | "hello":
                print("Why hello there?")
            case "help" | "?":
                print("Available commands: start, stop, reload, status, help")
            case _:
                print(f"Unknown command: {cmd}")

async def main():
    """
    Main entry point:
    - Starts the bot in a separate thread.
    - Launches the interactive console for commands.
    """
    # Start the bot in a separate daemon thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    # Enter the console loop
    await console_loop()

if __name__ == "__main__":
    asyncio.run(main())