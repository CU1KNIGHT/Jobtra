from fastapi import APIRouter
import settings as app_settings
from config import BASE_URL

# ── Config ────────────────────────────────────────────────────────────────────

router = APIRouter(tags=["config"])


@router.get("/api/config")
def get_config():
    s = app_settings.get_settings()
    return {"base_url": BASE_URL, "active_provider": s["provider"]}
