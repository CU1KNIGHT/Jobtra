#!/usr/bin/env bash
# One-time installer for macOS / Linux. Creates a local Python environment and
# installs dependencies. Safe to re-run. Double-click in a file manager, or:
#   bash install.sh
set -euo pipefail

# Work from the project root (this script lives there).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "▶ Jobtra — installer"

# Find a suitable Python 3 (>= 3.9).
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && \
     "$c" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo "✗ Python 3.9+ is required but was not found."
  echo "  Install it from https://www.python.org/downloads/ and run this again."
  exit 1
fi
echo "▶ Using $("$PY" --version)"

echo "▶ Creating virtual environment (.venv)…"
"$PY" -m venv .venv
./.venv/bin/python -m pip install --upgrade pip >/dev/null

echo "▶ Installing dependencies…"
./.venv/bin/python -m pip install -r App/requirements.txt

# Seed the env file so API keys have a home (optional to fill in).
if [ ! -f App/.env ]; then
  cp App/.env.example App/.env
  echo "▶ Created App/.env — add Anthropic/OpenAI keys there if you use them."
fi

echo ""
echo "✓ Installed. To start the app, double-click 'start-jobtra.command'"
echo "  (macOS) or run:  bash start-jobtra.command"
