import db

VALID_PROVIDERS = {"ollama", "anthropic", "openai"}


def get_settings() -> dict:
    conn = db.get_conn()
    row = conn.execute("SELECT provider, model FROM settings WHERE id = 1").fetchone()
    return dict(row)


def update_settings(provider: str, model: str) -> dict:
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"provider must be one of {sorted(VALID_PROVIDERS)}")
    conn = db.get_conn()
    conn.execute(
        "UPDATE settings SET provider = ?, model = ? WHERE id = 1",
        (provider, model),
    )
    conn.commit()
    return get_settings()
