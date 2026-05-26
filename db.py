import sqlite3
from typing import Optional

DB_PATH = "jobs.db"

_conn: Optional[sqlite3.Connection] = None


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _init_schema(_conn)
    return _conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            position      TEXT    NOT NULL,
            company       TEXT    NOT NULL,
            description   TEXT    DEFAULT '',
            date_applied  TEXT    NOT NULL,
            status        TEXT    NOT NULL DEFAULT 'open',
            address       TEXT    DEFAULT '',
            city          TEXT    DEFAULT '',
            hr_email      TEXT    DEFAULT '',
            hr_phone      TEXT    DEFAULT '',
            skills        TEXT    DEFAULT '',
            created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at    TEXT    NOT NULL DEFAULT (datetime('now')),
            CHECK (status IN ('open','applied','interview_done','rejected','rejected_after_interview','accepted'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id        INTEGER PRIMARY KEY CHECK (id = 1),
            provider  TEXT NOT NULL DEFAULT 'ollama',
            model     TEXT NOT NULL DEFAULT 'llama3.1:8b'
        )
    """)
    conn.execute(
        "INSERT OR IGNORE INTO settings (id, provider, model) VALUES (1, 'ollama', 'llama3.1:8b')"
    )
    conn.commit()


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def list_jobs() -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM jobs ORDER BY date_applied DESC"
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_job(job_id: int) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_dict(row) if row else None


def create_job(data: dict) -> dict:
    conn = get_conn()
    skills = ",".join(s.strip() for s in data.get("skills", "").split(",") if s.strip())
    cursor = conn.execute(
        """
        INSERT INTO jobs (position, company, description, date_applied, status,
                          address, city, hr_email, hr_phone, skills)
        VALUES (:position, :company, :description, :date_applied, :status,
                :address, :city, :hr_email, :hr_phone, :skills)
        """,
        {**data, "skills": skills},
    )
    conn.commit()
    return get_job(cursor.lastrowid)


def update_job(job_id: int, data: dict) -> Optional[dict]:
    conn = get_conn()
    skills = ",".join(s.strip() for s in data.get("skills", "").split(",") if s.strip())
    conn.execute(
        """
        UPDATE jobs
        SET position = :position,
            company = :company,
            description = :description,
            date_applied = :date_applied,
            status = :status,
            address = :address,
            city = :city,
            hr_email = :hr_email,
            hr_phone = :hr_phone,
            skills = :skills,
            updated_at = datetime('now')
        WHERE id = :id
        """,
        {**data, "skills": skills, "id": job_id},
    )
    conn.commit()
    return get_job(job_id)


def delete_job(job_id: int) -> bool:
    conn = get_conn()
    cursor = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn.commit()
    return cursor.rowcount > 0
