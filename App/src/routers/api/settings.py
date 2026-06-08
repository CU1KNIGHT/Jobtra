import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from util import VALID_PROVIDERS
import settings as app_settings

router = APIRouter(tags=["settings"])

class SettingsInput(BaseModel):
    provider: str
    model: str
    page_size: Optional[int] = None
    ollama_url: Optional[str] = None
    lmstudio_url: Optional[str] = None

@router.get("/api/settings")
def get_settings():
    s = app_settings.get_settings()
    key_status = {
        "ollama": None,
        "lmstudio": None,
        "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
        "openai": bool(os.getenv("OPENAI_API_KEY")),
    }
    return {**s, "providers": VALID_PROVIDERS, "key_status": key_status}


@router.put("/api/settings")
def update_settings(payload: SettingsInput):
    try:
        return app_settings.update_settings(
            payload.provider, payload.model, payload.page_size,
            ollama_url=payload.ollama_url, lmstudio_url=payload.lmstudio_url,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
