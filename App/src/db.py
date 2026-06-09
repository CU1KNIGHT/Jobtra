import json
import os
import re
import sqlite3
from typing import Optional
from cryptography.fernet import Fernet

from config import SECRET_KEY_PATH

# Location of the SQLite file. Defaults to "jobs.db" in the working directory
# (App/src) for local runs; override with DB_PATH to point at a mounted data
# volume in container/deployment setups.
DB_PATH = os.getenv("DB_PATH", "db/jobs.db")

_conn: Optional[sqlite3.Connection] = None


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        parent = os.path.dirname(DB_PATH)
        if parent:
            os.makedirs(parent, exist_ok=True)  # e.g. /data when DB_PATH is on a volume
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        _init_schema(conn)
        _conn = conn  # only assign after successful init so failed inits retry
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
            source_url    TEXT    DEFAULT '',
            source_text   TEXT    DEFAULT '',
            created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at    TEXT    NOT NULL DEFAULT (datetime('now')),
            CHECK (status IN ('open','applied','interview_invite','interview_done','rejected','rejected_after_interview','accepted'))
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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            filename    TEXT    NOT NULL,
            doc_type    TEXT    NOT NULL DEFAULT 'other',
            file_path   TEXT    NOT NULL,
            file_hash   TEXT    NOT NULL UNIQUE,
            file_size   INTEGER NOT NULL DEFAULT 0,
            uploaded_at TEXT    NOT NULL DEFAULT (datetime('now')),
            notes       TEXT    DEFAULT ''
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS job_documents (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id      INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE RESTRICT,
            attached_at TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE(job_id, document_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS email_accounts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            label        TEXT    NOT NULL,
            imap_host    TEXT    NOT NULL,
            imap_port    INTEGER NOT NULL DEFAULT 993,
            username     TEXT    NOT NULL,
            password_enc TEXT    NOT NULL DEFAULT '',
            last_sync_at TEXT,
            active       INTEGER NOT NULL DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS email_messages (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id     INTEGER NOT NULL REFERENCES email_accounts(id) ON DELETE CASCADE,
            uid            TEXT    NOT NULL,
            subject        TEXT    DEFAULT '',
            sender         TEXT    DEFAULT '',
            received_at    TEXT    NOT NULL,
            body_text      TEXT    DEFAULT '',
            direction      TEXT    NOT NULL DEFAULT 'incoming',
            relevance      TEXT    NOT NULL DEFAULT 'pending',
            processed_at   TEXT,
            linked_job_id  INTEGER REFERENCES jobs(id),
            llm_status     TEXT,
            llm_raw        TEXT,
            UNIQUE(account_id, uid)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS city_coords (
            city      TEXT    PRIMARY KEY,
            lat       REAL,
            lng       REAL,
            cached_at TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)
    _migrate(conn)
    conn.commit()


_DEFAULT_EMAIL_KEYWORDS = json.dumps([
    "application", "interview", "offer", "reject", "congratulations",
    "unfortunately", "position", "role", "hiring", "thank you for applying",
    "next steps", "assessment", "onboarding", "move forward",
])


def _migrate(conn: sqlite3.Connection) -> None:
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
    for col in ("source_url", "source_text", "whatsapp", "telegram", "hours_per_week", "languages", "source_email_id", "job_type", "work_mode"):
        if col not in cols:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} TEXT DEFAULT ''")

    email_cols = {row["name"] for row in conn.execute("PRAGMA table_info(email_messages)")}
    if "direction" not in email_cols:
        conn.execute("ALTER TABLE email_messages ADD COLUMN direction TEXT NOT NULL DEFAULT 'incoming'")

    settings_cols = {row["name"] for row in conn.execute("PRAGMA table_info(settings)")}
    for col in ("email_ollama_model", "email_sync_interval", "email_keywords", "fernet_key",
                "email_provider", "ollama_url", "lmstudio_url"):
        if col not in settings_cols:
            conn.execute(f"ALTER TABLE settings ADD COLUMN {col} TEXT")
    # page size for the jobs/email lists; INTEGER with a default so existing rows backfill.
    if "page_size" not in settings_cols:
        conn.execute("ALTER TABLE settings ADD COLUMN page_size INTEGER NOT NULL DEFAULT 25")

    # The status CHECK constraint can't be altered in place, so databases
    # created before a status was added need the jobs table rebuilt. Reuse the
    # existing definition (which may carry migration-added columns) and only
    # swap the table name and the status list.
    jobs_sql_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='jobs'"
    ).fetchone()
    if jobs_sql_row and "'interview_done'" in jobs_sql_row["sql"] \
            and "'interview_invite'" not in jobs_sql_row["sql"]:
        cols = ", ".join(row["name"] for row in conn.execute("PRAGMA table_info(jobs)"))
        new_sql = re.sub(
            r"CREATE TABLE( IF NOT EXISTS)? jobs\b",
            r"CREATE TABLE\1 jobs_new",
            jobs_sql_row["sql"],
            count=1,
        ).replace("'interview_done'", "'interview_invite','interview_done'")
        conn.commit()  # close any open implicit transaction so the PRAGMA applies
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN")
        conn.execute(new_sql)
        conn.execute(f"INSERT INTO jobs_new ({cols}) SELECT {cols} FROM jobs")
        conn.execute("DROP TABLE jobs")
        conn.execute("ALTER TABLE jobs_new RENAME TO jobs")
        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON")

    # Remove orphaned document links left behind by job deletions that
    # happened while foreign-key enforcement was off (so ON DELETE CASCADE
    # never fired). These inflated document usage counts.
    conn.execute("""
        DELETE FROM job_documents
        WHERE job_id NOT IN (SELECT id FROM jobs)
    """)


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def list_jobs() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("""
        SELECT j.*,
               (SELECT COUNT(*) FROM job_documents WHERE job_id = j.id) AS doc_count
        FROM jobs j
        ORDER BY j.date_applied DESC
    """).fetchall()
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
                          address, city, hr_email, hr_phone, skills,
                          whatsapp, telegram, hours_per_week, languages,
                          source_url, source_text, job_type, work_mode)
        VALUES (:position, :company, :description, :date_applied, :status,
                :address, :city, :hr_email, :hr_phone, :skills,
                :whatsapp, :telegram, :hours_per_week, :languages,
                :source_url, :source_text, :job_type, :work_mode)
        """,
        {**data, "skills": skills,
         "whatsapp": data.get("whatsapp", ""),
         "telegram": data.get("telegram", ""),
         "hours_per_week": data.get("hours_per_week", ""),
         "languages": data.get("languages", ""),
         "source_url": data.get("source_url", ""),
         "source_text": data.get("source_text", ""),
         "job_type": data.get("job_type", ""),
         "work_mode": data.get("work_mode", "")},
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
            whatsapp = :whatsapp,
            telegram = :telegram,
            hours_per_week = :hours_per_week,
            languages = :languages,
            source_url = :source_url,
            source_text = :source_text,
            job_type = :job_type,
            work_mode = :work_mode,
            updated_at = datetime('now')
        WHERE id = :id
        """,
        {**data, "skills": skills,
         "whatsapp": data.get("whatsapp", ""),
         "telegram": data.get("telegram", ""),
         "hours_per_week": data.get("hours_per_week", ""),
         "languages": data.get("languages", ""),
         "source_url": data.get("source_url", ""),
         "source_text": data.get("source_text", ""),
         "job_type": data.get("job_type", ""),
         "work_mode": data.get("work_mode", ""),
         "id": job_id},
    )
    conn.commit()
    return get_job(job_id)


def update_parsed_fields(job_id: int, parsed: dict) -> Optional[dict]:
    """Update only the parser-produced fields; preserve date_applied, status, id, created_at."""
    conn = get_conn()
    skills = ",".join(s.strip() for s in parsed.get("skills", "").split(",") if s.strip())
    conn.execute(
        """
        UPDATE jobs
        SET position = :position,
            company = :company,
            description = :description,
            address = :address,
            city = :city,
            hr_email = :hr_email,
            hr_phone = :hr_phone,
            skills = :skills,
            whatsapp = :whatsapp,
            telegram = :telegram,
            hours_per_week = :hours_per_week,
            languages = :languages,
            source_url = CASE WHEN :source_url != '' THEN :source_url ELSE source_url END,
            source_text = CASE WHEN :source_text != '' THEN :source_text ELSE source_text END,
            updated_at = datetime('now')
        WHERE id = :id
        """,
        {
            "position": parsed.get("position", ""),
            "company": parsed.get("company", ""),
            "description": parsed.get("description", ""),
            "address": parsed.get("address", ""),
            "city": parsed.get("city", ""),
            "hr_email": parsed.get("hr_email", ""),
            "hr_phone": parsed.get("hr_phone", ""),
            "skills": skills,
            "whatsapp": parsed.get("whatsapp", ""),
            "telegram": parsed.get("telegram", ""),
            "hours_per_week": parsed.get("hours_per_week", ""),
            "languages": parsed.get("languages", ""),
            "source_url": parsed.get("source_url", ""),
            "source_text": parsed.get("source_text", ""),
            "id": job_id,
        },
    )
    conn.commit()
    return get_job(job_id)


def delete_job(job_id: int) -> bool:
    conn = get_conn()
    cursor = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn.commit()
    return cursor.rowcount > 0


def update_job_status(job_id: int, status: str) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE jobs SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (status, job_id),
    )
    conn.commit()


# ── Documents ────────────────────────────────────────────────────────────────

def get_document(doc_id: int) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    return _row_to_dict(row) if row else None


def get_document_by_hash(file_hash: str) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM documents WHERE file_hash = ?", (file_hash,)).fetchone()
    return _row_to_dict(row) if row else None


def list_documents(job_id: Optional[int] = None) -> list[dict]:
    conn = get_conn()
    if job_id is not None:
        rows = conn.execute("""
            SELECT d.*, jd.attached_at,
                   (SELECT COUNT(*) FROM job_documents jc
                    JOIN jobs j ON j.id = jc.job_id
                    WHERE jc.document_id = d.id) AS usage_count
            FROM documents d
            JOIN job_documents jd ON jd.document_id = d.id
            WHERE jd.job_id = ?
            ORDER BY jd.attached_at DESC
        """, (job_id,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT d.*,
                   (SELECT COUNT(*) FROM job_documents jc
                    JOIN jobs j ON j.id = jc.job_id
                    WHERE jc.document_id = d.id) AS usage_count
            FROM documents d
            ORDER BY d.uploaded_at DESC
        """).fetchall()
    return [_row_to_dict(r) for r in rows]


def create_document(data: dict) -> dict:
    conn = get_conn()
    cursor = conn.execute(
        """INSERT INTO documents (filename, doc_type, file_path, file_hash, file_size, notes)
           VALUES (:filename, :doc_type, :file_path, :file_hash, :file_size, :notes)""",
        {
            "filename": data["filename"],
            "doc_type": data.get("doc_type", "other"),
            "file_path": data["file_path"],
            "file_hash": data["file_hash"],
            "file_size": data.get("file_size", 0),
            "notes": data.get("notes", ""),
        },
    )
    conn.commit()
    return get_document(cursor.lastrowid)


def delete_document(doc_id: int) -> bool:
    conn = get_conn()
    cursor = conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
    return cursor.rowcount > 0


def count_job_documents(doc_id: int) -> int:
    conn = get_conn()
    row = conn.execute(
        """SELECT COUNT(*) AS cnt FROM job_documents jd
           JOIN jobs j ON j.id = jd.job_id
           WHERE jd.document_id = ?""",
        (doc_id,),
    ).fetchone()
    return row["cnt"] if row else 0


def get_jobs_for_document(doc_id: int) -> list[dict]:
    conn = get_conn()
    rows = conn.execute("""
        SELECT j.id, j.position, j.company FROM jobs j
        JOIN job_documents jd ON jd.job_id = j.id
        WHERE jd.document_id = ?
    """, (doc_id,)).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_job_documents(job_id: int) -> list[dict]:
    return list_documents(job_id=job_id)


def attach_document_to_job(job_id: int, document_id: int) -> dict:
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO job_documents (job_id, document_id) VALUES (?, ?)",
        (job_id, document_id),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM job_documents WHERE job_id = ? AND document_id = ?",
        (job_id, document_id),
    ).fetchone()
    return _row_to_dict(row)


def detach_document_from_job(job_id: int, document_id: int) -> bool:
    conn = get_conn()
    cursor = conn.execute(
        "DELETE FROM job_documents WHERE job_id = ? AND document_id = ?",
        (job_id, document_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def get_job_doc_count(job_id: int) -> int:
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM job_documents WHERE job_id = ?", (job_id,)
    ).fetchone()
    return row["cnt"] if row else 0


# ── Email Accounts ────────────────────────────────────────────────────────────

def list_email_accounts(active_only: bool = False) -> list[dict]:
    conn = get_conn()
    if active_only:
        rows = conn.execute(
            "SELECT * FROM email_accounts WHERE active = 1 ORDER BY id"
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM email_accounts ORDER BY id").fetchall()
    return [_row_to_dict(r) for r in rows]


def get_email_account(account_id: int) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM email_accounts WHERE id = ?", (account_id,)).fetchone()
    return _row_to_dict(row) if row else None


def create_email_account(data: dict) -> dict:
    conn = get_conn()
    cursor = conn.execute(
        """INSERT INTO email_accounts (label, imap_host, imap_port, username, password_enc, active)
           VALUES (:label, :imap_host, :imap_port, :username, :password_enc, :active)""",
        {
            "label": data["label"],
            "imap_host": data["imap_host"],
            "imap_port": int(data.get("imap_port", 993)),
            "username": data["username"],
            "password_enc": data.get("password_enc", ""),
            "active": int(data.get("active", 1)),
        },
    )
    conn.commit()
    return get_email_account(cursor.lastrowid)


def update_email_account(account_id: int, data: dict) -> Optional[dict]:
    conn = get_conn()
    conn.execute(
        """UPDATE email_accounts
           SET label = :label, imap_host = :imap_host, imap_port = :imap_port,
               username = :username, active = :active
           WHERE id = :id""",
        {
            "label": data["label"],
            "imap_host": data["imap_host"],
            "imap_port": int(data.get("imap_port", 993)),
            "username": data["username"],
            "active": int(data.get("active", 1)),
            "id": account_id,
        },
    )
    conn.commit()
    return get_email_account(account_id)


def update_email_account_password(account_id: int, password_enc: str) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE email_accounts SET password_enc = ? WHERE id = ?",
        (password_enc, account_id),
    )
    conn.commit()


def delete_email_account(account_id: int) -> bool:
    conn = get_conn()
    cursor = conn.execute("DELETE FROM email_accounts WHERE id = ?", (account_id,))
    conn.commit()
    return cursor.rowcount > 0


def update_email_account_sync_time(account_id: int) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE email_accounts SET last_sync_at = datetime('now') WHERE id = ?",
        (account_id,),
    )
    conn.commit()


def reset_email_account_sync_time(account_id: int) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE email_accounts SET last_sync_at = NULL WHERE id = ?",
        (account_id,),
    )
    conn.commit()


# ── Email Messages ────────────────────────────────────────────────────────────

def list_email_messages(
    relevance: Optional[str] = None,
    account_id: Optional[int] = None,
    job_id: Optional[int] = None,
) -> list[dict]:
    conn = get_conn()
    where, params = [], []
    if relevance:
        where.append("relevance = ?")
        params.append(relevance)
    if account_id:
        where.append("account_id = ?")
        params.append(account_id)
    if job_id is not None:
        where.append("linked_job_id = ?")
        params.append(job_id)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    rows = conn.execute(
        f"SELECT * FROM email_messages {clause} ORDER BY received_at DESC",
        params,
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_email_message(msg_id: int) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM email_messages WHERE id = ?", (msg_id,)).fetchone()
    return _row_to_dict(row) if row else None


def create_email_message(data: dict) -> dict:
    conn = get_conn()
    cursor = conn.execute(
        """INSERT OR IGNORE INTO email_messages
           (account_id, uid, subject, sender, received_at, body_text, direction, relevance)
           VALUES (:account_id, :uid, :subject, :sender, :received_at, :body_text, :direction, :relevance)""",
        {
            "account_id": data["account_id"],
            "uid": data["uid"],
            "subject": data.get("subject", ""),
            "sender": data.get("sender", ""),
            "received_at": data["received_at"],
            "body_text": data.get("body_text", ""),
            "direction": data.get("direction", "incoming"),
            "relevance": data.get("relevance", "pending"),
        },
    )
    conn.commit()
    return get_email_message(cursor.lastrowid)


def update_email_message(msg_id: int, data: dict) -> None:
    conn = get_conn()
    allowed = {"relevance", "processed_at", "linked_job_id", "llm_status", "llm_raw"}
    sets = ", ".join(f"{k} = ?" for k in data if k in allowed)
    vals = [v for k, v in data.items() if k in allowed]
    if not sets:
        return
    conn.execute(f"UPDATE email_messages SET {sets} WHERE id = ?", vals + [msg_id])
    conn.commit()


def email_message_exists(account_id: int, uid: str) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM email_messages WHERE account_id = ? AND uid = ?",
        (account_id, uid),
    ).fetchone()
    return row is not None


# Legal-form / generic tokens that shouldn't count toward a company match.
_COMPANY_STOPWORDS = {
    "gmbh", "mbh", "ag", "kg", "ohg", "se", "co", "inc", "ltd", "llc", "plc",
    "bv", "nv", "sa", "srl", "gbr", "ug", "kgaa",
    "steuerberatungsgesellschaft", "steuerberatung", "gesellschaft",
    "group", "holding", "the",
}


def _normalize_company(name: str) -> tuple[str, list[str]]:
    """Lowercase, strip punctuation/legal suffixes. Returns (joined, tokens)."""
    s = re.sub(r"[^a-z0-9äöüß ]+", " ", (name or "").lower())
    tokens = [t for t in s.split() if t and t not in _COMPANY_STOPWORDS]
    return " ".join(tokens), tokens


def find_job_by_hr_email(addr: str) -> Optional[dict]:
    """Find the job whose hr_email matches `addr` (case-insensitive). Used to
    auto-link emails we sent to a job's HR contact. Prefers active, recent jobs."""
    addr = (addr or "").strip().lower()
    if not addr:
        return None
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT * FROM jobs
        WHERE TRIM(LOWER(hr_email)) = ?
        ORDER BY (status IN ('rejected', 'rejected_after_interview', 'accepted')) ASC,
                 date_applied DESC
        """,
        (addr,),
    ).fetchall()
    return _row_to_dict(rows[0]) if rows else None


def find_matching_job(company: str, position: str) -> Optional[dict]:
    conn = get_conn()
    target, _ = _normalize_company(company)
    if not target:
        return None
    # Match against all jobs so emails still link to finalized applications;
    # prefer still-active jobs, then most recent.
    rows = conn.execute(
        """
        SELECT * FROM jobs
        ORDER BY (status IN ('rejected', 'rejected_after_interview', 'accepted')) ASC,
                 date_applied DESC
        """
    ).fetchall()
    candidates = [_row_to_dict(r) for r in rows]
    for j in candidates:
        jc, _ = _normalize_company(j.get("company") or "")
        if not jc:
            continue
        # Match either direction, ignoring legal suffixes / extra words:
        # "kalkül" (job) ⊂ "kalkül dresden gmbh" (email) and vice versa.
        if target in jc or jc in target:
            return j
    return None


# ── Dashboard analytics ───────────────────────────────────────────────────────

def _parse_hours(value: str):
    m = re.search(r"\d+", value or "")
    return int(m.group()) if m else None


def _classify_type(position: str, description: str, hours: str) -> str:
    """Best-effort job-type bucket. The schema has no type column, so we infer
    it from text keywords (EN/DE), falling back to hours_per_week."""
    t = f"{position} {description}".lower()
    if any(k in t for k in ("intern", "praktik", "werkstud", "working student")):
        return "internship"
    if any(k in t for k in ("freelance", "freiberuf", "contractor")):
        return "freelance"
    # "befristet" = fixed-term, but must not match inside "unbefristet" (permanent)
    if any(k in t for k in ("contract", "fixed-term", "temporary")) or \
            ("befristet" in t and "unbefristet" not in t):
        return "contract"
    if any(k in t for k in ("mini-job", "mini job", "minijob", "marginal employment", "geringfügig")):
        return "mini-job"
    if any(k in t for k in ("part-time", "part time", "teilzeit")):
        return "part-time"
    if any(k in t for k in ("full-time", "full time", "vollzeit", "permanent", "unbefristet")):
        return "full-time"
    h = _parse_hours(hours)
    if h is not None:
        return "full-time" if h >= 35 else "part-time"
    return "unspecified"


def get_dashboard_stats() -> dict:
    """Read-only aggregates over the jobs table for the dashboard."""
    conn = get_conn()

    def _count(where: str = "", params: tuple = ()) -> int:
        clause = f" WHERE {where}" if where else ""
        return conn.execute(f"SELECT COUNT(*) AS c FROM jobs{clause}", params).fetchone()["c"]

    total = _count()
    active = _count("status IN ('open','applied','interview_invite')")
    interviews = _count("status IN ('interview_invite','interview_done')")
    rejected = _count("status IN ('rejected','rejected_after_interview')")
    rejection_rate = round(rejected / total, 2) if total else 0.0

    by_month = [dict(r) for r in conn.execute(
        "SELECT substr(date_applied,1,7) AS month, COUNT(*) AS count "
        "FROM jobs WHERE date_applied IS NOT NULL AND TRIM(date_applied) != '' "
        "GROUP BY month ORDER BY month"
    ).fetchall()]
    by_status = [dict(r) for r in conn.execute(
        "SELECT status, COUNT(*) AS count FROM jobs GROUP BY status ORDER BY count DESC"
    ).fetchall()]
    by_city = [dict(r) for r in conn.execute(
        "SELECT city, COUNT(*) AS count FROM jobs WHERE TRIM(COALESCE(city,'')) != '' "
        "GROUP BY city ORDER BY count DESC"
    ).fetchall()]
    by_position = [dict(r) for r in conn.execute(
        "SELECT position, COUNT(*) AS count FROM jobs WHERE TRIM(COALESCE(position,'')) != '' "
        "GROUP BY position ORDER BY count DESC"
    ).fetchall()]

    recent = [dict(r) for r in conn.execute(
        "SELECT id, position, company, status, date_applied, city FROM jobs "
        "ORDER BY date_applied DESC, id DESC LIMIT 6"
    ).fetchall()]

    type_counts: dict[str, int] = {}
    for r in conn.execute("SELECT position, description, hours_per_week, job_type FROM jobs").fetchall():
        explicit = (r["job_type"] or "").strip()
        bucket = explicit or _classify_type(r["position"] or "", r["description"] or "", r["hours_per_week"] or "")
        type_counts[bucket] = type_counts.get(bucket, 0) + 1
    by_type = [{"type": k, "count": v}
               for k, v in sorted(type_counts.items(), key=lambda kv: kv[1], reverse=True)]

    return {
        "summary": {
            "total": total,
            "active": active,
            "interviews": interviews,
            "rejection_rate": rejection_rate,
        },
        "by_month": by_month,
        "by_status": by_status,
        "by_type": by_type,
        "by_city": by_city,
        "by_position": by_position,
        "recent": recent,
    }


def get_cached_city_coords(city: str) -> Optional[dict]:
    """Return the cached row for a city (lat/lng may be None for a known miss),
    or None if the city has never been geocoded."""
    row = get_conn().execute(
        "SELECT lat, lng FROM city_coords WHERE city = ?", (city,)
    ).fetchone()
    return dict(row) if row else None


def save_city_coords(city: str, lat: Optional[float], lng: Optional[float]) -> None:
    """Upsert a geocoding result. Storing (None, None) negatively caches a miss
    so we don't re-query an unresolvable city on every dashboard load."""
    conn = get_conn()
    conn.execute(
        "INSERT INTO city_coords (city, lat, lng) VALUES (?, ?, ?) "
        "ON CONFLICT(city) DO UPDATE SET lat = excluded.lat, lng = excluded.lng, "
        "cached_at = datetime('now')",
        (city, lat, lng),
    )
    conn.commit()


def get_email_sync_status() -> dict:
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) AS c FROM email_messages").fetchone()["c"]
    pending = conn.execute(
        "SELECT COUNT(*) AS c FROM email_messages WHERE relevance = 'pending'"
    ).fetchone()["c"]
    last_sync = conn.execute(
        "SELECT MAX(last_sync_at) AS t FROM email_accounts WHERE active = 1"
    ).fetchone()["t"]
    return {"total": total, "pending": pending, "last_sync_at": last_sync}


# ── Email Settings ────────────────────────────────────────────────────────────

def get_email_settings() -> dict:
    conn = get_conn()
    # self-heal: if a migration didn't run yet (e.g. existing connection from
    # before a schema change), apply it now rather than crashing
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(settings)")}
    for col in ("email_ollama_model", "email_sync_interval", "email_keywords", "fernet_key", "email_provider"):
        if col not in existing:
            conn.execute(f"ALTER TABLE settings ADD COLUMN {col} TEXT")
    conn.commit()
    row = conn.execute(
        "SELECT email_provider, email_ollama_model, email_sync_interval, email_keywords FROM settings WHERE id = 1"
    ).fetchone()
    if not row:
        return {
            # provider/model blank means "follow the global parser settings"
            "email_provider": "",
            "email_ollama_model": "",
            "email_sync_interval": 60,
            "email_keywords": json.loads(_DEFAULT_EMAIL_KEYWORDS),
        }
    return {
        "email_provider": row["email_provider"] or "",
        "email_ollama_model": row["email_ollama_model"] or "",
        "email_sync_interval": int(row["email_sync_interval"] or 60),
        "email_keywords": json.loads(row["email_keywords"]) if row["email_keywords"] else json.loads(_DEFAULT_EMAIL_KEYWORDS),
    }


def update_email_settings(data: dict) -> dict:
    conn = get_conn()
    allowed = {"email_provider", "email_ollama_model", "email_sync_interval", "email_keywords"}
    sets = []
    vals = []
    for k, v in data.items():
        if k in allowed:
            sets.append(f"{k} = ?")
            vals.append(json.dumps(v) if k == "email_keywords" else v)
    if sets:
        conn.execute(f"UPDATE settings SET {', '.join(sets)} WHERE id = 1", vals)
        conn.commit()
    return get_email_settings()


def get_or_create_fernet_key() -> bytes:
    """Return the Fernet key, stored in a standalone file (config.SECRET_KEY_PATH).

    The key is intentionally kept outside jobs.db so it never sits alongside the
    data it protects. Older installs that stored the key in the DB are migrated
    to the file (so existing encrypted passwords still decrypt) and the DB copy
    is then cleared.
    """
    path = SECRET_KEY_PATH
    if path.exists():
        return path.read_bytes().strip()

    # Migrate a legacy key from the DB if present, else mint a fresh one.
    legacy = ""
    try:
        row = get_conn().execute("SELECT fernet_key FROM settings WHERE id = 1").fetchone()
        legacy = (row["fernet_key"] if row else "") or ""
    except sqlite3.OperationalError:
        pass  # column never existed on this DB
    key = legacy.encode() if legacy else Fernet.generate_key()

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(key)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # best-effort; e.g. on filesystems without POSIX perms

    if legacy:
        conn = get_conn()
        conn.execute("UPDATE settings SET fernet_key = '' WHERE id = 1")
        conn.commit()
    return key
