from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

import db


class EmailSettingsInput(BaseModel):
    email_provider: Optional[str] = None
    email_ollama_model: Optional[str] = None
    email_sync_interval: Optional[int] = None
    email_keywords: Optional[list[str]] = None


router = APIRouter(tags=["email", "settings"])


@router.get("/api/email/settings")
def get_email_settings():
    return db.get_email_settings()


@router.put("/api/email/settings")
def update_email_settings(payload: EmailSettingsInput):
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    return db.update_email_settings(data)
