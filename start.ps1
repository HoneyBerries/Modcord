# Find the first activate script in any subdirectory
$activatePath = Get-ChildItem -Recurse -Filter activate.ps1 | Select-Object -First 1

if (-not $activatePath) {
    Write-Host "No virtual environment activate script found. Exiting."
    exit 1
}

$venvDir = Split-Path $activatePath.Directory.FullName -Parent
Write-Host "Activating virtual environment: $venvDir"

# Activate the virtual environment
& $activatePath.FullName

# Run your Python script
python src/modcord/main.py