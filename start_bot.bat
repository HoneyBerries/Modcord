@echo off
echo Starting Discord Moderation Bot...
echo Make sure you have set up your .env file with the bot token!
echo.

REM Check if .env file exists
if not exist ".env" (
    echo ERROR: .env file not found!
    echo Please copy .env.template to .env and add your Discord bot token.
    pause
    exit /b 1
)

REM Run the bot
C:\Users\Henry-New-Account\Documents\Python_Projects\Modcord\.venv\Scripts\python.exe run_bot.py
pause
