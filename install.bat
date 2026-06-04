@echo off
REM One-time installer for Windows. Creates a local Python environment and
REM installs dependencies. Safe to re-run. Double-click this file to run.
setlocal
cd /d "%~dp0"

echo Jobtra - installer
echo.

REM Find Python: prefer the py launcher, fall back to python on PATH.
set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
  echo Python 3 is required but was not found.
  echo Install it from https://www.python.org/downloads/
  echo ^(tick "Add Python to PATH" during setup^), then run this again.
  echo.
  pause
  exit /b 1
)

echo Creating virtual environment (.venv)...
%PY% -m venv .venv
if errorlevel 1 goto :fail

.venv\Scripts\python -m pip install --upgrade pip
echo Installing dependencies...
.venv\Scripts\python -m pip install -r App\requirements.txt
if errorlevel 1 goto :fail

if not exist App\.env copy App\.env.example App\.env >nul

echo.
echo Installed. Double-click start-jobtra.bat to launch the app.
pause
exit /b 0

:fail
echo.
echo Installation failed. See the messages above.
pause
exit /b 1
