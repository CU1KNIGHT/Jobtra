import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
import db as _db


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch):
    """Every test gets a clean in-memory SQLite database."""
    monkeypatch.setattr(_db, "DB_PATH", ":memory:")
    monkeypatch.setattr(_db, "_conn", None)
    yield
    conn = _db._conn
    monkeypatch.setattr(_db, "_conn", None)
    if conn:
        try:
            conn.close()
        except Exception:
            pass


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from server import app
    return TestClient(app)


@pytest.fixture
def job_payload():
    return {
        "position": "Backend Engineer",
        "company": "Acme Corp",
        "description": "Build scalable APIs",
        "date_applied": "2026-01-01",
        "status": "open",
        "address": "123 Main St",
        "city": "Berlin",
        "hr_email": "hr@acme.com",
        "hr_phone": "+49 30 1234",
        "whatsapp": "",
        "telegram": "",
        "hours_per_week": "40",
        "languages": "English",
        "skills": "Python,FastAPI",
        "source_url": "https://example.com/job",
        "source_text": "",
    }
