#!/bin/bash
# Change to the directory where this script is located (project root)
cd "$(dirname "$0")"

# If already in a venv, skip venv logic and run bot
if [ -n "$VIRTUAL_ENV" ]; then
    VENV_DIR="$VIRTUAL_ENV"
    if [ -f "$VENV_DIR/pyvenv.cfg" ] && [ -x "$VENV_DIR/bin/python" ]; then
        echo "Using already-active virtual environment: $VENV_DIR"
        echo "Running bot..."
        python src/modcord/main.py
        exit $?
    fi
fi

# Find all bin/activate scripts that are inside a bin directory and a real Python venv (with pyvenv.cfg and python)
mapfile -t ALL_ACTIVATES < <(find . -type f -name activate -path "*/bin/activate")
ACTIVATES=()
for ACTIVATE in "${ALL_ACTIVATES[@]}"; do
    PARENT_DIR=$(basename "$(dirname "$ACTIVATE")")
    if [ "$PARENT_DIR" = "bin" ]; then
        VENV_DIR="$(dirname "$(dirname "$ACTIVATE")")"
        if [ -f "$VENV_DIR/pyvenv.cfg" ] && [ -x "$VENV_DIR/bin/python" ]; then
            ACTIVATES+=("$ACTIVATE:$VENV_DIR")
        fi
    fi
done
FOUND=0

for ENTRY in "${ACTIVATES[@]}"; do
    ACTIVATE="${ENTRY%%:*}"
    VENV_DIR="${ENTRY#*:}"
    echo "Trying virtual environment: $VENV_DIR"
    source "$ACTIVATE"
    python --version >/dev/null 2>&1
    if [ $? -eq 0 ]; then
        echo "Successfully activated: $VENV_DIR"
        echo "Running bot..."
        python src/modcord/main.py
        exit $?
    else
        echo "Activation failed for: $VENV_DIR"
    fi
done

if [ $FOUND -eq 0 ]; then
    echo "No working Python virtual environment found."
    read -p "Would you like to create a new venv and install dependencies? (Y/N): " CREATEVENV
    if [[ "$CREATEVENV" =~ ^[Yy]$ ]]; then
        python -m venv venv
        source venv/bin/activate
        pip install -r requirements.txt
        echo "Running bot..."
        python src/modcord/main.py
        exit $?
    else
        echo "Exiting."
        exit 1
    fi
fi
