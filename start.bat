@echo off
setlocal enabledelayedexpansion

REM Find the first activate.bat file in any subdirectory
for /r %%F in (activate.bat) do (
    set "ACTIVATE_PATH=%%F"
    goto :found
)

echo No virtual environment activate script found. Exiting.
exit /b 1

:found
REM Get the virtual environment directory (two levels up)
for %%A in ("%ACTIVATE_PATH%") do (
    set "SCRIPTS_DIR=%%~dpA"
)
for %%B in ("%SCRIPTS_DIR%..\") do (
    set "VENV_DIR=%%~fB"
)

echo Activating virtual environment: %VENV_DIR%

REM Activate the environment
call "%ACTIVATE_PATH%"

REM Run your Python script
python src\modcord\main.py
