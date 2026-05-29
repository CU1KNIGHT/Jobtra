import db


# ── Jobs ──────────────────────────────────────────────────────────────────────

def test_list_jobs_empty():
    assert db.list_jobs() == []


def test_create_and_get_job(job_payload):
    job = db.create_job(job_payload)
    assert job["id"] is not None
    assert job["position"] == "Backend Engineer"
    assert job["company"] == "Acme Corp"
    assert job["status"] == "open"

    fetched = db.get_job(job["id"])
    assert fetched["id"] == job["id"]
    assert fetched["position"] == job["position"]


def test_get_nonexistent_job():
    assert db.get_job(9999) is None


def test_list_jobs_returns_all(job_payload):
    db.create_job(job_payload)
    db.create_job({**job_payload, "company": "Beta Inc"})
    jobs = db.list_jobs()
    assert len(jobs) == 2
    companies = {j["company"] for j in jobs}
    assert companies == {"Acme Corp", "Beta Inc"}


def test_update_job(job_payload):
    job = db.create_job(job_payload)
    updated = db.update_job(job["id"], {**job_payload, "position": "Senior Engineer", "status": "applied"})
    assert updated["position"] == "Senior Engineer"
    assert updated["status"] == "applied"
    assert db.get_job(job["id"])["position"] == "Senior Engineer"


def test_delete_job(job_payload):
    job = db.create_job(job_payload)
    assert db.delete_job(job["id"]) is True
    assert db.get_job(job["id"]) is None


def test_delete_nonexistent_job():
    assert db.delete_job(9999) is False


def test_update_job_status(job_payload):
    job = db.create_job(job_payload)
    db.update_job_status(job["id"], "interview_done")
    assert db.get_job(job["id"])["status"] == "interview_done"


def test_skills_normalised_on_create(job_payload):
    job = db.create_job({**job_payload, "skills": " Python , FastAPI , Docker "})
    assert job["skills"] == "Python,FastAPI,Docker"


# ── Settings ──────────────────────────────────────────────────────────────────

def test_settings_row_exists_with_defaults():
    conn = db.get_conn()
    row = conn.execute("SELECT provider, model FROM settings WHERE id = 1").fetchone()
    assert row["provider"] == "ollama"
    assert row["model"] == "llama3.1:8b"


# ── Email settings ────────────────────────────────────────────────────────────

def test_get_email_settings_defaults():
    s = db.get_email_settings()
    assert s["email_provider"] == "ollama"
    assert s["email_sync_interval"] == 60
    assert isinstance(s["email_keywords"], list)
    assert len(s["email_keywords"]) > 0


def test_update_email_settings():
    db.update_email_settings({"email_ollama_model": "gemma2:2b", "email_sync_interval": 30})
    s = db.get_email_settings()
    assert s["email_ollama_model"] == "gemma2:2b"
    assert s["email_sync_interval"] == 30


def test_update_email_keywords():
    db.update_email_settings({"email_keywords": ["interview", "offer"]})
    s = db.get_email_settings()
    assert s["email_keywords"] == ["interview", "offer"]


# ── Email accounts ────────────────────────────────────────────────────────────

def _make_account(**kwargs):
    defaults = {
        "label": "Personal",
        "imap_host": "imap.gmail.com",
        "imap_port": 993,
        "username": "test@gmail.com",
        "password_enc": "enc_secret",
        "active": 1,
    }
    return db.create_email_account({**defaults, **kwargs})


def test_create_and_get_email_account():
    account = _make_account()
    assert account["id"] is not None
    assert account["label"] == "Personal"

    fetched = db.get_email_account(account["id"])
    assert fetched["username"] == "test@gmail.com"


def test_list_email_accounts():
    _make_account(label="Gmail")
    _make_account(label="Work", username="work@corp.com")
    accounts = db.list_email_accounts()
    assert len(accounts) == 2


def test_delete_email_account():
    account = _make_account()
    assert db.delete_email_account(account["id"]) is True
    assert db.get_email_account(account["id"]) is None


def test_reset_account_sync_time():
    account = _make_account()
    db.update_email_account_sync_time(account["id"])
    assert db.get_email_account(account["id"])["last_sync_at"] is not None
    db.reset_email_account_sync_time(account["id"])
    assert db.get_email_account(account["id"])["last_sync_at"] is None


# ── Email messages ────────────────────────────────────────────────────────────

def _make_message(account_id, uid="uid-001", **kwargs):
    defaults = {
        "account_id": account_id,
        "uid": uid,
        "subject": "Interview invite",
        "sender": "hr@co.com",
        "received_at": "2026-01-01T10:00:00",
        "body_text": "You are invited.",
        "relevance": "pending",
    }
    return db.create_email_message({**defaults, **kwargs})


def test_email_message_exists():
    account = _make_account()
    assert db.email_message_exists(account["id"], "uid-001") is False
    _make_message(account["id"], "uid-001")
    assert db.email_message_exists(account["id"], "uid-001") is True


def test_list_email_messages_by_relevance():
    account = _make_account()
    _make_message(account["id"], "uid-001", relevance="pending")
    _make_message(account["id"], "uid-002", relevance="relevant")
    _make_message(account["id"], "uid-003", relevance="irrelevant")

    assert len(db.list_email_messages(relevance="pending")) == 1
    assert len(db.list_email_messages(relevance="relevant")) == 1
    assert len(db.list_email_messages()) == 3


def test_update_email_message():
    account = _make_account()
    msg = _make_message(account["id"])
    db.update_email_message(msg["id"], {"relevance": "relevant", "llm_status": "interview_invite"})
    updated = db.get_email_message(msg["id"])
    assert updated["relevance"] == "relevant"
    assert updated["llm_status"] == "interview_invite"


# ── find_matching_job ─────────────────────────────────────────────────────────

def test_find_matching_job_by_company(job_payload):
    db.create_job({**job_payload, "company": "Google LLC", "status": "applied"})
    matched = db.find_matching_job("google", "engineer")
    assert matched is not None
    assert "Google" in matched["company"]


def test_find_matching_job_no_match(job_payload):
    db.create_job({**job_payload, "company": "Google LLC"})
    assert db.find_matching_job("Amazon", "engineer") is None


def test_find_matching_job_skips_closed(job_payload):
    db.create_job({**job_payload, "company": "Acme Corp", "status": "rejected"})
    assert db.find_matching_job("acme", "engineer") is None


# ── Email sync status ─────────────────────────────────────────────────────────

def test_get_email_sync_status_empty():
    status = db.get_email_sync_status()
    assert status["total"] == 0
    assert status["pending"] == 0
    assert status["last_sync_at"] is None


def test_get_email_sync_status_with_messages():
    account = _make_account()
    _make_message(account["id"], "uid-001", relevance="pending")
    _make_message(account["id"], "uid-002", relevance="relevant")
    status = db.get_email_sync_status()
    assert status["total"] == 2
    assert status["pending"] == 1
