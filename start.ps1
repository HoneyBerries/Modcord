

# Change to the directory where this script is located (project root)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $scriptDir
Clear-Host

# If already in a venv, skip venv logic and run bot
if ($env:VIRTUAL_ENV) {
    $activeVenv = $env:VIRTUAL_ENV
    $pyvenv = Join-Path $activeVenv 'pyvenv.cfg'
    $pyexe = Join-Path $activeVenv 'Scripts/python.exe'
    if ((Test-Path $pyvenv) -and (Test-Path $pyexe)) {
        Write-Host "Using already-active virtual environment: $activeVenv"
        Write-Host "Running bot..."
        python src/modcord/main.py
        exit $LASTEXITCODE
    }
}

# Find all activate.ps1 scripts in Scripts folder with pyvenv.cfg and python.exe
$activatePaths = Get-ChildItem -Recurse -Filter Activate.ps1 -ErrorAction SilentlyContinue
$validActivates = @()
foreach ($activatePath in $activatePaths) {
    $scriptsLeaf = $activatePath.Directory.Name
    if ($scriptsLeaf -ieq 'Scripts') {
        $venvDir = Split-Path $activatePath.Directory.FullName -Parent
        try {
            $venvDirResolved = (Resolve-Path -Path $venvDir).ProviderPath
        } catch {
            $venvDirResolved = $venvDir
        }
        $pyvenv = Join-Path $venvDirResolved 'pyvenv.cfg'
        $pyexe = Join-Path $venvDirResolved 'Scripts/python.exe'
        if ((Test-Path $pyvenv) -and (Test-Path $pyexe)) {
            $validActivates += [PSCustomObject]@{ Activate=(Resolve-Path $activatePath.FullName).ProviderPath; VenvDir=$venvDirResolved }
        }
    }
}

$found = $false
foreach ($item in $validActivates) {
    $activatePath = $item.Activate
    $venvDir = $item.VenvDir
    Write-Host "Trying virtual environment: $venvDir"
    & "$activatePath"
    python --version > $null 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Successfully activated: $venvDir"
        $found = $true
        Write-Host "Running bot..."
        python src/modcord/main.py
        exit $LASTEXITCODE
    } else {
        Write-Host "Activation failed for: $venvDir"
    }
}

if (-not $found) {
    Write-Host "No working Python virtual environment found."
    $response = Read-Host "Would you like to create a new venv and install dependencies? (Y/N)"
    if ($response -eq 'Y' -or $response -eq 'y') {
        python -m venv venv
        .\venv\Scripts\Activate.ps1
        pip install -r requirements.txt
        Write-Host "Running bot..."
        python src/modcord/main.py
        exit $LASTEXITCODE
    } else {
        Write-Host "Exiting."
        exit 1
    }
}