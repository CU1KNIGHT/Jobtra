@echo off
REM ============================================================
REM  Jobtra - Windows install & run launcher
REM  Double-click this file to set up (first run) and start the app.
REM  Re-running it just starts the app; it won't reinstall.
REM ============================================================
setlocal enabledelayedexpansion

REM Always work from the folder this script lives in
cd /d "%~dp0"

set "VENV_DIR=.venv"
set "PYEXE=%VENV_DIR%\Scripts\python.exe"

echo.
echo ============================================
echo   Jobtra - Windows launcher
echo ============================================
echo.

REM --- 1. Locate Python -------------------------------------------------
where py >nul 2>&1
if %errorlevel%==0 (
    set "PY_LAUNCH=py -3"
) else (
    where python >nul 2>&1
    if !errorlevel!==0 (
        set "PY_LAUNCH=python"
    ) else (
        echo [ERROR] Python 3 was not found on this system.
        echo Install it from https://www.python.org/downloads/
        echo and tick "Add python.exe to PATH" during setup, then run this again.
        echo.
        pause
        exit /b 1
    )
)

REM --- 1b. Check Python version (need 3.13 or higher) ------------------
set "MIN_MAJOR=3"
set "MIN_MINOR=13"

for /f "tokens=2" %%V in ('%PY_LAUNCH% --version 2^>^&1') do set "PYVER=%%V"
for /f "tokens=1,2 delims=." %%A in ("%PYVER%") do (
    set "PY_MAJOR=%%A"
    set "PY_MINOR=%%B"
)

set "PY_TOO_OLD="
if %PY_MAJOR% LSS %MIN_MAJOR% set "PY_TOO_OLD=1"
if %PY_MAJOR%==%MIN_MAJOR% if %PY_MINOR% LSS %MIN_MINOR% set "PY_TOO_OLD=1"

if defined PY_TOO_OLD (
    echo [WARN] Python %PYVER% was found, but Jobtra needs Python %MIN_MAJOR%.%MIN_MINOR% or higher.
    echo.

    where winget >nul 2>&1
    if !errorlevel!==0 (
        echo You can upgrade automatically using winget.
        set /p "DO_UPGRADE=Upgrade Python to the latest version now? [Y/N] "
        if /i "!DO_UPGRADE!"=="Y" (
            echo [setup] Installing the latest Python via winget ...
            winget install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements
            echo.
            echo [done] Python was installed. Please close this window and run this
            echo        script again so the new Python is picked up.
            echo.
            pause
            exit /b 0
        ) else (
            echo [ERROR] A newer Python is required to continue. Exiting.
            pause
            exit /b 1
        )
    ) else (
        echo winget is not available on this system, so Python cannot be upgraded
        echo automatically. Please install Python %MIN_MAJOR%.%MIN_MINOR% or higher manually from:
        echo     https://www.python.org/downloads/
        echo Tick "Add python.exe to PATH" during setup, then run this script again.
        echo.
        pause
        exit /b 1
    )
) else (
    echo [ok] Python %PYVER% detected.
)

REM --- 2. Create the virtual environment (first run only) ---------------
if not exist "%PYEXE%" (
    echo [setup] Creating virtual environment in "%VENV_DIR%" ...
    %PY_LAUNCH% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERROR] Failed to create the virtual environment.
        pause
        exit /b 1
    )

    echo [setup] Upgrading pip ...
    "%PYEXE%" -m pip install --upgrade pip

    echo [setup] Installing dependencies ...
    "%PYEXE%" -m pip install -r "App\requirements.txt"
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
) else (
    echo [ok] Virtual environment already present, skipping install.
)

REM --- 3. Create .env from the example if missing -----------------------
if not exist ".env" (
    if exist ".env.example" (
        echo [setup] Creating .env from .env.example ...
        copy /y ".env.example" ".env" >nul
    )
)

REM --- 4. Start the server and open the browser -------------------------
echo.
echo [run] Starting Jobtra at http://localhost:8000
echo       (Close this window or press Ctrl+C to stop the app.)
echo.

REM Open the browser shortly after the server starts
start "" cmd /c "timeout /t 3 >nul & start http://localhost:8000"

cd "App\src"
"..\..\%VENV_DIR%\Scripts\python.exe" -m uvicorn server:app --host 127.0.0.1 --port 8000

echo.
echo [stopped] Jobtra has stopped.
pause
endlocal
