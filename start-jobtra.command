#!/usr/bin/env bash
# ============================================================
#  Jobtra - macOS / Linux start launcher
#  Starts the app using the environment created by install.sh.
#  Double-click in Finder, or run:  bash start-jobtra.command
#  (Run install.sh first if you haven't set up the app yet.)
# ============================================================
set -euo pipefail

# Always work from the folder this script lives in.
cd "$(dirname "$0")"

VENV_DIR=".venv"
PYEXE="$VENV_DIR/bin/python"

echo
echo "============================================"
echo "  Jobtra - starting"
echo "============================================"
echo

# --- 1. Make sure the app has been installed --------------------------
if [ ! -x "$PYEXE" ]; then
    echo "[ERROR] No virtual environment found in \"$VENV_DIR\"."
    echo "        Run the installer first:  bash install.sh"
    exit 1
fi

# --- 2. Resolve the URL from config (single source of truth) ----------
cd "App/src"
PYBIN="../../$VENV_DIR/bin/python"
URL="$("$PYBIN" -c "from config import BASE_URL; print(BASE_URL)")"

# --- 3. Open the browser shortly after the server starts --------------
open_browser() {
    sleep 3
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$URL" >/dev/null 2>&1 || true   # Linux
    elif command -v open >/dev/null 2>&1; then
        open "$URL" >/dev/null 2>&1 || true        # macOS
    fi
}
open_browser &

# --- 4. Start the server ----------------------------------------------
echo "[run] Starting Jobtra at $URL"
echo "      (Press Ctrl+C to stop the app.)"
echo

exec "$PYBIN" server.py
