import os

from .openai import OpenAIProvider


class LMStudioProvider(OpenAIProvider):
    """Local LLM served by LM Studio's OpenAI-compatible server.

    Runs on the user's machine (default http://localhost:1234), needs no API
    key, and exposes whatever models are currently loaded — so no model filter.
    """
    name = "lmstudio"
    label = "LM Studio"
    model_prefix = None  # show every loaded model

    def __init__(self, base_url: str = None):
        # Prefer an explicit URL (from settings); otherwise fall back to
        # LMSTUDIO_BASE_URL or LM Studio's default local server. Root only —
        # "/v1/..." is appended by the base class.
        default = os.getenv("LMSTUDIO_BASE_URL") or "http://localhost:1234"
        self.api_base = (base_url or "").rstrip("/") or default

    def _headers(self) -> dict:
        # Local server: no authentication, so don't send an Authorization header.
        return {"content-type": "application/json"}
