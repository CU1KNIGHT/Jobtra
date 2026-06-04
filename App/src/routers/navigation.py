import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from starlette.responses import HTMLResponse, RedirectResponse

import db
from config import BASE_URL, UI_DIR, VERSION

router = APIRouter(tags=["navigation"])

# Append ?v=<version> to every <script src="..."> and <link href="..."> so a
# new release busts cached assets. Matches the src/href on script/link tags only.
_ASSET_RE = re.compile(r'(<(?:script|link)\b[^>]*?\b(?:src|href)=")([^"]*)(")', re.IGNORECASE)


def _add_version(html: str) -> str:
    def repl(m: re.Match) -> str:
        url = m.group(2)
        sep = "&" if "?" in url else "?"
        return f"{m.group(1)}{url}{sep}v={VERSION}{m.group(3)}"

    return _ASSET_RE.sub(repl, html)


def _serve(filename: str) -> str:
    """Read a UI page and apply the shared serve-time substitutions."""
    html = Path(f"{UI_DIR}/{filename}").read_text()
    html = html.replace("__BASE_URL__", BASE_URL)
    return _add_version(html)


@router.get("/favicon.ico", include_in_schema=False)
def favicon():
    # Browsers/tools request /favicon.ico at the root; point them at the SVG.
    return RedirectResponse(url="/static/favicon.svg")


@router.get("/", response_class=HTMLResponse)
def index():
    # Dashboard is the home page.
    return _serve("dashboard.html")


@router.get("/jobs", response_class=HTMLResponse)
def jobs_page():
    return _serve("index.html")


@router.get("/settings", response_class=HTMLResponse)
def settings_page():
    return _serve("settings.html")


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_detail_page(job_id: int):
    if db.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _serve("job_detail.html")


@router.get("/documents", response_class=HTMLResponse)
def documents_page():
    return _serve("documents.html")


@router.get("/email", response_class=HTMLResponse)
def email_page():
    return _serve("email.html")


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page():
    return _serve("dashboard.html")
