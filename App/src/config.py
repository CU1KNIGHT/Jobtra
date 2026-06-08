import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
ROOT_DIR = Path(__file__).parent.parent.parent
UI_DIR = ROOT_DIR / "ui"

# App version, read from the VERSION file at the project root.
try:
    VERSION = (ROOT_DIR / "VERSION").read_text(encoding="utf-8").strip()
except OSError:
    VERSION = "0.0.0"

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8001"))
BASE_URL = f"http://{HOST}:{PORT}"

DOCS_DIR = Path(os.path.expanduser(os.getenv("DOCS_DIR", "~/.jobtra/docs")))
DOCS_DIR.mkdir(parents=True, exist_ok=True)

# Fernet key for encrypting stored email-account passwords. Kept in a standalone
# file (default: alongside jobs.db) so the key never lives inside the DB it
# protects. Override with SECRET_KEY_PATH.
SECRET_KEY_PATH = Path(os.path.expanduser(os.getenv("SECRET_KEY_PATH", "secret.key")))