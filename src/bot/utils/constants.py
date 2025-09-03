"""
Constants for the bot.
"""

import discord

PERMANENT_DURATION = "Till the end of time"

DURATIONS = {
    "60 secs": 60,
    "5 mins": 5 * 60,
    "10 mins": 10 * 60,
    "30 mins": 30 * 60,
    "1 hour": 60 * 60,
    "2 hours": 2 * 60 * 60,
    "1 day": 24 * 60 * 60,
    "1 week": 7 * 24 * 60 * 60,
    PERMANENT_DURATION: 0,
}

DURATION_CHOICES = list(DURATIONS.keys())

DELETE_MESSAGE_CHOICES = [
    discord.OptionChoice(name="Don't Delete Any", value=0),
    discord.OptionChoice(name="Previous Hour", value=60 * 60),
    discord.OptionChoice(name="Previous 6 Hours", value=6 * 60 * 60),
    discord.OptionChoice(name="Previous 12 Hours", value=12 * 60 * 60),
    discord.OptionChoice(name="Previous 24 Hours", value=24 * 60 * 60),
    discord.OptionChoice(name="Previous 3 Days", value=3 * 24 * 60 * 60),
    discord.OptionChoice(name="Previous 7 Days", value=7 * 24 * 60 * 60),
]
