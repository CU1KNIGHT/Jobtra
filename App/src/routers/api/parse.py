from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from starlette.responses import JSONResponse

import db
import settings as app_settings
from fetcher import fetch_as_text, FetchError
from parse import _run_parse
from providers.base import ProviderAuthError, ProviderUnavailable, ProviderBadOutput, ProviderTimeout
from util import Job


class ParseInput(BaseModel):
    text: Optional[str] = None
    url: Optional[str] = None


router = APIRouter(tags=["parse"])


@router.post("/api/jobs/{job_id}/reparse", response_model=Job)
async def reparse_job(job_id: int):
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    source_url = job.get("source_url", "")
    source_text = job.get("source_text", "")

    if not source_url and not source_text:
        raise HTTPException(
            status_code=400,
            detail="This job has no source to re-parse from. Re-parse only works on jobs created via Paste/URL.",
        )

    s = app_settings.get_settings()
    provider_name = s["provider"]

    fetched_text = source_text
    new_source_text = ""
    if source_url:
        try:
            fetched_text = await fetch_as_text(source_url)
            new_source_text = fetched_text
        except FetchError:
            # Fall back to stored source_text
            if not source_text:
                raise HTTPException(
                    status_code=502,
                    detail="Could not re-fetch the original URL and no cached text is available.",
                )
            fetched_text = source_text

    try:
        parsed = await _run_parse(
            fetched_text,
            source_url=source_url,
            source_text=new_source_text or source_text,
        )
    except Exception as e:
        resp = _provider_error_response(e, provider_name)
        raise HTTPException(status_code=resp.status_code, detail=resp.body.decode())

    updated = db.update_parsed_fields(job_id, parsed)

    return updated


@router.post("/api/parse")
async def parse_job(payload: ParseInput):
    if payload.url and payload.text:
        raise HTTPException(400, "Provide either text or url, not both")
    if not payload.url and not payload.text:
        raise HTTPException(400, "Provide text or url")

    s = app_settings.get_settings()
    provider_name = s["provider"]

    # Fetch URL if needed
    source_url = ""
    fetched_text = payload.text or ""
    if payload.url:
        source_url = payload.url
        try:
            fetched_text = await fetch_as_text(payload.url)
        except FetchError as e:
            return JSONResponse(
                status_code=e.status,
                content={"error": str(e), "hint": e.hint or "Try copy-pasting the page text instead."},
            )

    try:
        result = await _run_parse(fetched_text, source_url=source_url, source_text=fetched_text)
        return result
    except Exception as e:
        return _provider_error_response(e, provider_name)


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
