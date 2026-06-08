import os

import db
from util import VALID_PROVIDERS  # single source of truth

DEFAULT_PAGE_SIZE = 25
MIN_PAGE_SIZE = 5
MAX_PAGE_SIZE = 500

# Default base URLs for the local providers, used when the user hasn't set a
# custom one. LM Studio still honours LMSTUDIO_BASE_URL from .env as its default.
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_LMSTUDIO_URL = os.getenv("LMSTUDIO_BASE_URL") or "http://localhost:1234"

# Map provider name -> (settings column, default URL) for local providers whose
# endpoint is user-configurable.
LOCAL_PROVIDER_URLS = {
    "ollama": ("ollama_url", DEFAULT_OLLAMA_URL),
    "lmstudio": ("lmstudio_url", DEFAULT_LMSTUDIO_URL),
}


def _coerce_page_size(value, fallback=DEFAULT_PAGE_SIZE) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(MIN_PAGE_SIZE, min(MAX_PAGE_SIZE, n))


def get_settings() -> dict:
    conn = db.get_conn()
    row = conn.execute(
        "SELECT provider, model, page_size, ollama_url, lmstudio_url "
        "FROM settings WHERE id = 1"
    ).fetchone()
    s = dict(row)
    s["page_size"] = _coerce_page_size(s.get("page_size"))
    for name, (col, default) in LOCAL_PROVIDER_URLS.items():
        s[col] = (s.get(col) or "").strip() or default
    return s


def local_provider_url(name: str) -> str:
    """Configured base URL for a local provider ('ollama'/'lmstudio')."""
    col, default = LOCAL_PROVIDER_URLS[name]
    return get_settings().get(col, default)


def update_settings(provider: str, model: str, page_size=None,
                    ollama_url=None, lmstudio_url=None) -> dict:
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"provider must be one of {sorted(VALID_PROVIDERS)}")

    fields = {"provider": provider, "model": model}
    if page_size is not None:
        fields["page_size"] = _coerce_page_size(page_size)
    if ollama_url is not None:
        fields["ollama_url"] = ollama_url.strip()
    if lmstudio_url is not None:
        fields["lmstudio_url"] = lmstudio_url.strip()

    assignments = ", ".join(f"{col} = ?" for col in fields)  # keys are fixed, not user input
    conn = db.get_conn()
    conn.execute(f"UPDATE settings SET {assignments} WHERE id = 1", tuple(fields.values()))
    conn.commit()
    return get_settings()
