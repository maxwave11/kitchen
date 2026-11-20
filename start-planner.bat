@echo off
setlocal
cd /d "%~dp0" || exit /b 1
set "PYTHONUTF8=1"

py -3.11 -c "import sys" >nul 2>&1
if errorlevel 1 (
    echo Python 3.11 was not found. Install it with the Windows Python Launcher.
    pause
    exit /b 1
)

py -3.11 -c "import yaml" >nul 2>&1
if errorlevel 1 (
    echo PyYAML is missing. Run: py -3.11 -m pip install PyYAML
    pause
    exit /b 1
)

py -3.11 tools\room3d\serve.py --open
if errorlevel 1 (
    pause
    exit /b 1
)
