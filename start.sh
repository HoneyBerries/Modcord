#!/bin/bash
# Change to the directory where this script is located (project root)
cd "$(dirname "$0")"

# Function to install uv if not present
install_uv() {
    if command -v uv &> /dev/null; then
        echo "uv is already installed."
        return 0
    fi

    echo "uv not found. Installing uv..."
    if ! command -v curl &> /dev/null; then
        echo "curl not found. Please install uv manually: https://github.com/astral-sh/uv#installation"
        return 1
    fi

    if ! curl -LsSf https://astral.sh/uv/install.sh | sh; then
        echo "Failed to install uv via curl."
        return 1
    fi

    # Source the appropriate shell profile to update PATH
    CURRENT_SHELL=$(basename "$SHELL")
    case "$CURRENT_SHELL" in
        bash)
            [ -f "$HOME/.bashrc" ] && source "$HOME/.bashrc"
            ;;
        zsh)
            [ -f "$HOME/.zshrc" ] && source "$HOME/.zshrc"
            ;;
        fish)
            [ -f "$HOME/.config/fish/config.fish" ] && source "$HOME/.config/fish/config.fish"
            ;;
        *)
            echo "Unknown shell: $CURRENT_SHELL. Please restart your terminal or source your profile manually if uv is not found."
            ;;
    esac

    if command -v uv &> /dev/null; then
        echo "uv installed successfully."
        return 0
    else
        echo "uv installation completed, but uv not found in PATH. Please restart your terminal or source your shell profile."
        return 1
    fi
}

# Install uv if not present
echo "Checking for uv..."
if ! install_uv; then
    echo "Failed to ensure uv is available."
    exit 1
fi

echo "Starting program ..."
uv run src/modcord/main.py