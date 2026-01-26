# Change to the directory where this script is located (project root)
Set-Location -Path $PSScriptRoot

function Install-Uv {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Write-Host "uv is already installed."
        return $true
    }

    Write-Host "uv not found. Installing uv..."
    if (-not (Get-Command curl -ErrorAction SilentlyContinue)) {
        Write-Host "curl not found. Please install uv manually: https://github.com/astral-sh/uv#installation"
        return $false
    }

    try {
        Invoke-WebRequest -Uri "https://astral.sh/uv/install.ps1" -UseBasicParsing | Invoke-Expression
    } catch {
        Write-Host "Failed to install uv via curl."
        return $false
    }

    $uvCmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($uvCmd) {
        Write-Host "uv installed successfully."
        return $true
    }

    # Refresh PATH for common install locations
    $env:PATH = @(
        $env:PATH,
        "$env:USERPROFILE\.cargo\bin",
        "$env:USERPROFILE\.local\bin"
    ) -join ';'

    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Write-Host "uv installed successfully."
        return $true
    }

    Write-Host "uv installation completed, but uv not found in PATH. Please restart your terminal."
    return $false
}

Write-Host "Checking for uv..."
if (-not (Install-Uv)) {
    Write-Host "Failed to ensure uv is available."
    exit 1
}

Write-Host "Starting program ..."
uv run src/modcord/main.py