import db

VALID_PROVIDERS = {"ollama", "anthropic", "openai"}

DEFAULT_PAGE_SIZE = 25
MIN_PAGE_SIZE = 5
MAX_PAGE_SIZE = 500


def _coerce_page_size(value, fallback=DEFAULT_PAGE_SIZE) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(MIN_PAGE_SIZE, min(MAX_PAGE_SIZE, n))


def get_settings() -> dict:
    conn = db.get_conn()
    row = conn.execute("SELECT provider, model, page_size FROM settings WHERE id = 1").fetchone()
    s = dict(row)
    s["page_size"] = _coerce_page_size(s.get("page_size"))
    return s


def update_settings(provider: str, model: str, page_size=None) -> dict:
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"provider must be one of {sorted(VALID_PROVIDERS)}")
    conn = db.get_conn()
    if page_size is None:
        conn.execute(
            "UPDATE settings SET provider = ?, model = ? WHERE id = 1",
            (provider, model),
        )
    else:
        conn.execute(
            "UPDATE settings SET provider = ?, model = ?, page_size = ? WHERE id = 1",
            (provider, model, _coerce_page_size(page_size)),
        )
    conn.commit()
    return get_settings()
