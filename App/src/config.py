import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
UI_DIR = Path(__file__).parent.parent.parent / "ui"

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
BASE_URL = f"http://{HOST}:{PORT}"

DOCS_DIR = Path(os.path.expanduser(os.getenv("DOCS_DIR", "~/.job-tracker/docs")))
DOCS_DIR.mkdir(parents=True, exist_ok=True)