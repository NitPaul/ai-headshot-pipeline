@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo  [X] The tool is not set up yet on this computer.
    echo      Please double-click  setup.bat  first.
    echo.
    pause
    exit /b 1
)

set "PYTHONPATH=%~dp0src"
call ".venv\Scripts\python.exe" -m wegro_headshot %*

echo.
pause
