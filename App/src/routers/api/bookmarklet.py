from fastapi import APIRouter
from pydantic import BaseModel
from starlette.responses import JSONResponse

import db
from parse import _run_parse
from routers.api.parse import _provider_error_response
import settings as app_settings
from util import Job

router = APIRouter(tags=["bookmarklet","api"])

class BookmarkletInput(BaseModel):
    text: str
    url: str = ""


@router.post("/api/parse-from-bookmarklet", response_model=Job, status_code=201)
async def parse_from_bookmarklet(payload: BookmarkletInput):
    if not payload.text or not payload.text.strip():
        return JSONResponse(status_code=400, content={"error": "Empty page text"})

    s = app_settings.get_settings()
    provider_name = s["provider"]
    text = payload.text[:12000]

    try:
        parsed = await _run_parse(text, source_url=payload.url, source_text=text)
    except Exception as e:
        return _provider_error_response(e, provider_name)

    return db.create_job(parsed)
