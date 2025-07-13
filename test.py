import asyncio
import collections
import datetime
import logging
import os
import subprocess
import sys

import discord
import yaml
from dotenv import load_dotenv


# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

logger = logging.getLogger(__name__)

load_dotenv()

with open("config.yml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)
SERVER_RULES = config["server_rules"]

bot = discord.Bot(intents=discord.Intents.all())

# Rate limiting per user (not currently implemented)
user_last_processed = {}

# Add in-memory history storage
db_history = collections.defaultdict(lambda: collections.deque(maxlen=12))


@bot.slash_command(name="reload", description="Hot-reload the bot")
async def reload_bot(ctx: discord.Interaction):
    if not hasattr(ctx, "user") or not isinstance(ctx.user, discord.Member) or not ctx.user.guild_permissions.administrator:
        await ctx.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    await ctx.response.send_message("Reloading bot...")
    channel_id = getattr(ctx.channel, "id", None)
    if channel_id is not None:
        with open("reload_success.flag", "w") as f:
            f.write(str(channel_id))
    else:
        logger.warning("ctx.channel is None, cannot write reload flag.")
    await asyncio.to_thread(subprocess.Popen, [sys.executable, sys.argv[0]])
    os._exit(0)

@bot.slash_command(name="test", description="Checks to see if I am online")
async def test(ctx):
    await ctx.respond(f"I am working! \nLatency: {(bot.latency * 1000):.2f} ms.")


@bot.event
async def on_ready():
    logger.info(f"Bot connected as {bot.user} at {datetime.datetime.now()}")

    if os.path.exists("reload_success.flag"):
        try:
            with open("reload_success.flag", "r") as f:
                channel_id = int(f.read().strip())
            channel = bot.get_channel(channel_id)
            if isinstance(channel, (discord.TextChannel, discord.Thread)):
                await channel.send("✅ Bot reloaded successfully!")
        except Exception as e:
            logger.error(f"Failed to send reload success message: {e}")
        finally:
            os.remove("reload_success.flag")

def main():
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        logger.error("DISCORD_TOKEN environment variable not set")
        return
    
    bot.run(token)

if __name__ == "__main__":
    main()