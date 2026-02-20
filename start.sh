#!/bin/bash
# Change to the directory where this script is located (project root)
cd "$(dirname "$0")"

# Function to install uv if not present
install_uv() {
    if ! command -v uv &> /dev/null; then
        echo "uv not found. Installing uv..."
        if command -v curl &> /dev/null; then
            curl -LsSf https://astral.sh/uv/install.sh | sh
            if [ $? -ne 0 ]; then
                echo "Failed to install uv via curl"
                return 1
            fi
        else
            echo "curl not found. Please install uv manually: https://github.com/astral-sh/uv#installation"
            return 1
        fi
        
        # Source the shell profile to update PATH
        if [ -f "$HOME/.bashrc" ]; then
            source "$HOME/.bashrc"
        fi
        if [ -f "$HOME/.zshrc" ]; then
            source "$HOME/.zshrc"
        fi
    fi
    
    return 0
}

# Install uv if not present
echo "Checking for uv..."
if ! install_uv; then
    echo "Failed to ensure uv is available."
    exit 1
fi

echo "Running bot via uv..."

uv run modcord

exit $?