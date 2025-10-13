@echo off
setlocal enabledelayedexpansion
set "FOUND=0"
set "PY_OK=0"

REM If already in a venv, skip venv logic and run bot
if defined VIRTUAL_ENV (
    set "VENV_DIR=%VIRTUAL_ENV%"
    if exist "%VENV_DIR%\pyvenv.cfg" if exist "%VENV_DIR%\Scripts\python.exe" (
        echo Using already-active virtual environment: %VIRTUAL_ENV%
        echo Running bot...
        python src\modcord\main.py
        exit /b %ERRORLEVEL%
    )
)

REM Search and try activate.bat scripts in Scripts dir with pyvenv.cfg and python.exe
for /r %%F in (activate.bat) do (
    for %%G in ("%%~dpF.") do set "SCRIPTS_DIR=%%~nxG"
    if /I "!SCRIPTS_DIR!"=="Scripts" (
        for %%H in ("%%~dpF..") do set "VENV_DIR=%%~fH"
        pushd "!VENV_DIR!" >nul 2>&1
        set "VENV_DIR=!CD!"
        popd >nul 2>&1
        if exist "!VENV_DIR!\pyvenv.cfg" if exist "!VENV_DIR!\Scripts\python.exe" (
            echo Trying virtual environment: !VENV_DIR!
            call "%%~fF"
            python --version >nul 2>&1
            if not errorlevel 1 (
                set "FOUND=1"
                echo Successfully activated: !VENV_DIR!
                echo Running bot...
                python src\modcord\main.py
                exit /b %ERRORLEVEL%
            )
            echo Activation failed for: !VENV_DIR!
        )
    )
)

if !FOUND! equ 0 (
    echo No working Python virtual environment found.
    set /p CREATEVENV="Would you like to create a new venv and install dependencies? (Y/N): "
    if /i "!CREATEVENV!"=="Y" (
        python -m venv venv
        call venv\Scripts\activate.bat
        pip install -r requirements.txt
        echo Running bot...
        python src\modcord\main.py
        exit /b %ERRORLEVEL%
    ) else (
        echo Exiting.
        exit /b 1
    )
}
