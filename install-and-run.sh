#!/usr/bin/env bash
# ============================================================
#  Jobtra - macOS / Linux install & run launcher
#  Run ./install-and-run.sh to set up (first run) and start the app.
#  Re-running it just starts the app; it won't reinstall.
# ============================================================
set -euo pipefail

# Always work from the folder this script lives in
cd "$(dirname "$0")"

VENV_DIR=".venv"
PYEXE="$VENV_DIR/bin/python"

echo
echo "============================================"
echo "  Jobtra - macOS / Linux launcher"
echo "============================================"
echo

# --- 1. Locate Python 3 ------------------------------------------------
if command -v python3 >/dev/null 2>&1; then
    PY_LAUNCH="python3"
elif command -v python >/dev/null 2>&1; then
    PY_LAUNCH="python"
else
    echo "[ERROR] Python 3 was not found on this system."
    echo "  - macOS:  brew install python   (or https://www.python.org/downloads/)"
    echo "  - Linux:  sudo apt install python3 python3-venv   (or your distro's package)"
    exit 1
fi

# --- 2. Create the virtual environment (first run only) ----------------
if [ ! -x "$PYEXE" ]; then
    echo "[setup] Creating virtual environment in \"$VENV_DIR\" ..."
    "$PY_LAUNCH" -m venv "$VENV_DIR"

    echo "[setup] Upgrading pip ..."
    "$PYEXE" -m pip install --upgrade pip

    echo "[setup] Installing dependencies ..."
    "$PYEXE" -m pip install -r "App/requirements.txt"
else
    echo "[ok] Virtual environment already present, skipping install."
fi

# --- 3. Create .env from the example if missing ------------------------
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    echo "[setup] Creating .env from .env.example ..."
    cp ".env.example" ".env"
fi

# --- 4. Open the browser shortly after the server starts ---------------
open_browser() {
    sleep 3
    URL="http://localhost:8000"
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$URL" >/dev/null 2>&1 || true   # Linux
    elif command -v open >/dev/null 2>&1; then
        open "$URL" >/dev/null 2>&1 || true        # macOS
    fi
}
open_browser &

# --- 5. Start the server ----------------------------------------------
echo
echo "[run] Starting Jobtra at http://localhost:8000"
echo "      (Press Ctrl+C to stop the app.)"
echo

cd "App/src"
exec "../../$VENV_DIR/bin/python" -m uvicorn server:app --host 127.0.0.1 --port 8000
