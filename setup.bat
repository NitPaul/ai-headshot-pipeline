@echo off
setlocal
cd /d "%~dp0"

echo.
echo  ============================================================
echo    WeGro Headshot Tool  -  ONE TIME SETUP
echo  ============================================================
echo.
echo  This will take 5-10 minutes and needs an internet connection.
echo  You only ever have to do this once on this computer.
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo  [X] Python is not installed.
    echo.
    echo      Download it from https://www.python.org/downloads/
    echo      IMPORTANT: tick "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)

echo  [1/4] Creating a private Python environment...
if not exist ".venv" (
    python -m venv .venv
    if errorlevel 1 (
        echo  [X] Could not create the environment.
        pause
        exit /b 1
    )
)

echo  [2/4] Installing the required components...
call ".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
call ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo  [X] Installation failed. Check your internet connection and try again.
    pause
    exit /b 1
)

echo  [3/4] Downloading the face-matching model...
set "PYTHONPATH=%~dp0src"
call ".venv\Scripts\python.exe" -m wegro_headshot.setup_models
if errorlevel 1 (
    echo  [!] Could not download the face-matching model.
    echo      The tool will still work, but quality checking will be reduced.
)

echo  [4/4] Checking your settings...
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo.
    echo  ------------------------------------------------------------
    echo   ACTION NEEDED - you must add your free Google API key.
    echo  ------------------------------------------------------------
    echo   1. Go to  https://aistudio.google.com/apikey
    echo   2. Sign in and click "Create API key". It is free.
    echo   3. Copy the key.
    echo   4. A file called  .env  has just been created in this folder.
    echo      Open it with Notepad and paste your key after the = sign.
    echo.
    echo   Then you are ready. Run  run.bat  to start.
    echo  ------------------------------------------------------------
) else (
    echo.
    echo  Setup complete. You can now use  run.bat
)

echo.
pause
