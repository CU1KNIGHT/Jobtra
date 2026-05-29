
from typing import Optional
from fastapi import HTTPException, Query, APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

import db
import email_sync

from providers.base import (
    ProviderAuthError, ProviderBadOutput, ProviderTimeout, ProviderUnavailable,
)

class LinkEmailInput(BaseModel):
    job_id: int


def _provider_error_response(e: Exception, provider_name: str) -> JSONResponse:
    if isinstance(e, ProviderAuthError):
        key_name = "ANTHROPIC_API_KEY" if provider_name == "anthropic" else "OPENAI_API_KEY"
        return JSONResponse(status_code=401, content={"error": str(e), "hint": f"Add {key_name} to .env"})
    if isinstance(e, ProviderUnavailable):
        hint = "Start Ollama with: ollama serve" if provider_name == "ollama" else str(e)
        return JSONResponse(status_code=503, content={"error": str(e), "hint": hint})
    if isinstance(e, ProviderBadOutput):
        return JSONResponse(status_code=502, content={"error": "Model returned invalid JSON"})
    if isinstance(e, ProviderTimeout):
        return JSONResponse(status_code=504, content={"error": "Provider timed out"})
    return JSONResponse(status_code=500, content={"error": str(e)})


router = APIRouter(tags=["email", "messages"])


@router.get("/api/email/messages")
def list_email_messages(
    relevance: Optional[str] = Query(None),
    account_id: Optional[int] = Query(None),
    job_id: Optional[int] = Query(None),
):
    return db.list_email_messages(relevance=relevance, account_id=account_id, job_id=job_id)


@router.post("/api/email/process")
async def process_emails(relevance: str = "pending"):
    import settings as app_settings
    s = app_settings.get_settings()
    model = s.get("model", "llama3.1:8b")
    provider_name = s.get("provider", "ollama")

    async def stream():
        async for event in email_sync.process_pending_emails(model, provider_name):
            yield event.encode()

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.post("/api/email/messages/{msg_id}/process")
async def process_single_email(msg_id: int):
    msg = db.get_email_message(msg_id)
    if msg is None:
        raise HTTPException(404, "Message not found")
    import settings as app_settings
    s = app_settings.get_settings()
    model = s.get("model", "llama3.1:8b")
    provider_name = s.get("provider", "ollama")
    try:
        result = await email_sync.process_email_with_llm(msg, model, provider_name)
    except Exception as e:
        return _provider_error_response(e, provider_name)
    from datetime import datetime, timezone
    import json
    now = datetime.now(timezone.utc).isoformat()
    relevant = result.get("relevant", False)
    if not relevant:
        db.update_email_message(msg_id, {
            "relevance": "irrelevant", "processed_at": now, "llm_raw": json.dumps(result)
        })
        return {"id": msg_id, "relevance": "irrelevant"}
    llm_status = result.get("status")
    confidence = float(result.get("confidence", 0.0))
    db.update_email_message(msg_id, {
        "relevance": "relevant", "processed_at": now,
        "llm_status": llm_status, "llm_raw": json.dumps(result),
    })
    linked_job_id = None
    company = result.get("company") or ""
    position = result.get("position") or ""
    if company:
        matched = db.find_matching_job(company, position)
        if matched and confidence >= 0.85:
            new_status = email_sync.STATUS_MAP.get(llm_status)
            if new_status:
                db.update_job_status(matched["id"], new_status)
            db.update_email_message(msg_id, {"linked_job_id": matched["id"]})
            linked_job_id = matched["id"]
    return {
        "id": msg_id, "relevance": "relevant", "llm_status": llm_status,
        "confidence": confidence, "linked_job_id": linked_job_id,
        "company": company, "position": position, "notes": result.get("notes", ""),
    }


@router.post("/api/email/messages/{msg_id}/link")
def link_email_to_job(msg_id: int, payload: LinkEmailInput):
    if db.get_email_message(msg_id) is None:
        raise HTTPException(404, "Message not found")
    if db.get_job(payload.job_id) is None:
        raise HTTPException(404, "Job not found")
    db.update_email_message(msg_id, {"linked_job_id": payload.job_id})
    return {"linked_job_id": payload.job_id}


@router.delete("/api/email/messages/{msg_id}/link", status_code=204)
def unlink_email_from_job(msg_id: int):
    if db.get_email_message(msg_id) is None:
        raise HTTPException(404, "Message not found")
    db.update_email_message(msg_id, {"linked_job_id": None})
