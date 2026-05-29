from pathlib import Path

from fastapi import APIRouter, HTTPException
from starlette.responses import HTMLResponse

import db
from config import BASE_URL, UI_DIR

router = APIRouter(tags=["navigation"])


@router.get("/", response_class=HTMLResponse)
def index():
    print("test:")
    print(UI_DIR)
    html = Path(f"{UI_DIR}/index.html").read_text()
    return html.replace("__BASE_URL__", BASE_URL)


@router.get("/settings")
def settings_page():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/", status_code=302)


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_detail_page(job_id: int):
    if db.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")
    html = Path(f"{UI_DIR}/job_detail.html").read_text()
    return html.replace("__BASE_URL__", BASE_URL)


@router.get("/documents", response_class=HTMLResponse)
def documents_page():
    return Path(f"{UI_DIR}/documents.html").read_text()


@router.get("/email", response_class=HTMLResponse)
def email_page():
    return Path(f"{UI_DIR}/email.html").read_text()
