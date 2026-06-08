@echo off
REM ============================================================
REM  Jobtra - Windows start launcher
REM  Starts the app using the environment created by install.bat.
REM  Double-click this file to launch the app.
REM  (Run install.bat first if you haven't set up the app yet.)
REM ============================================================
setlocal enabledelayedexpansion

REM Always work from the folder this script lives in.
cd /d "%~dp0"

set "VENV_DIR=.venv"
set "PYEXE=%VENV_DIR%\Scripts\python.exe"

echo.
echo ============================================
echo   Jobtra - starting
echo ============================================
echo.

REM --- 1. Make sure the app has been installed --------------------------
if not exist "%PYEXE%" (
    echo [ERROR] No virtual environment found in "%VENV_DIR%".
    echo         Run the installer first: double-click install.bat
    echo.
    pause
    exit /b 1
)

REM --- 2. Start the server and open the browser -------------------------
cd "App\src"
set "PYBIN=..\..\%VENV_DIR%\Scripts\python.exe"

REM Resolve the URL from config (single source of truth)
for /f "delims=" %%U in ('"%PYBIN%" -c "from config import BASE_URL; print(BASE_URL)"') do set "URL=%%U"

echo [run] Starting Jobtra at %URL%
echo       (Close this window or press Ctrl+C to stop the app.)
echo.

REM Open the browser shortly after the server starts
start "" cmd /c "timeout /t 3 >nul & start %URL%"

"%PYBIN%" server.py

echo.
echo [stopped] Jobtra has stopped.
pause
endlocal
