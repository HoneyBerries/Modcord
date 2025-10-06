#!/bin/bash

# Find the first activate script in any subdirectory
ACTIVATE_PATH=$(find . -type f -path "*/bin/activate" | head -n 1)

if [ -z "$ACTIVATE_PATH" ]; then
    echo "No virtual environment activate script found. Exiting."
    exit 1
fi

VENV_DIR=$(dirname "$(dirname "$ACTIVATE_PATH")")
echo "Activating virtual environment: $VENV_DIR"
source "$ACTIVATE_PATH"

python src/modcord/main.py
