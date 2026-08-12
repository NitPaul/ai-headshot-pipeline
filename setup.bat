@echo off
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "tools\setup.ps1"

if errorlevel 1 (
    echo.
    echo  ------------------------------------------------------------
    echo   Setup did not finish. The message above says why.
    echo   If you are stuck, send that message to whoever set this up.
    echo  ------------------------------------------------------------
)

echo.
pause
