#!/bin/bash

# Activate the virtual environment and run the bot
VENV_DIR="venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "Virtual environment not found. Exiting."
    exit 1
fi

source "$VENV_DIR/bin/activate"

python src/modcord/main.py