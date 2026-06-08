import csv
import io
import json
import re
from datetime import date

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import ValidationError

import db
from util import Job, JobInput, VALID_STATUSES

router = APIRouter(tags=["job","api"])

_JOB_FIELDS = set(JobInput.model_fields.keys())

# Alternative column / key names accepted from other tools, mapped to our fields.
_FIELD_ALIASES = {
    "position":       {"title", "job_title", "jobtitle", "role", "job", "job_role", "position_title",
                       "stelle", "titel", "stellenbezeichnung", "jobtitel", "beruf"},
    "company":        {"employer", "company_name", "companyname", "organization", "organisation", "org",
                       "firma", "unternehmen", "arbeitgeber", "betrieb"},
    "date_applied":   {"date", "applied", "applied_date", "application_date", "applied_on", "date_of_application",
                       "datum", "beworben", "bewerbungsdatum", "beworben_am"},
    "status":         {"state", "stage", "application_status", "zustand"},
    "description":    {"desc", "notes", "summary", "details", "beschreibung", "notizen"},
    "address":        {"street", "location_address", "adresse", "anschrift"},
    "city":           {"location", "town", "place", "stadt", "ort"},
    "hr_email":       {"email", "contact_email", "recruiter_email", "hr_mail", "e_mail"},
    "hr_phone":       {"phone", "contact_phone", "recruiter_phone", "telephone", "tel", "telefon"},
    "whatsapp":       {"whatsapp_number", "wa"},
    "telegram":       {"telegram_handle", "tg"},
    "hours_per_week": {"hours", "weekly_hours", "stunden", "wochenstunden"},
    "languages":      {"language", "sprachen", "sprache"},
    "job_type":       {"type", "employment_type", "employmenttype", "contract_type",
                       "anstellungsart", "beschäftigungsart", "beschaeftigungsart", "arbeitszeit"},
    "work_mode":      {"work_arrangement", "workarrangement", "work_location", "location_type",
                       "remote_type", "arbeitsmodell", "arbeitsort", "arbeitsform"},
    "skills":         {"tags", "keywords", "skill", "fähigkeiten", "faehigkeiten", "kenntnisse"},
    "source_url":     {"url", "link", "job_url", "posting_url", "source_link", "quelle"},
    "source_text":    {"raw", "source"},
}
# alias (and the canonical name itself) -> canonical field
_ALIAS_TO_FIELD = {f: f for f in _JOB_FIELDS}
for _canon, _aliases in _FIELD_ALIASES.items():
    for _a in _aliases:
        _ALIAS_TO_FIELD[_a] = _canon

# Common external status vocabularies mapped onto our six statuses.
_STATUS_SYNONYMS = {
    "wishlist": "open", "saved": "open", "bookmarked": "open", "interested": "open",
    "to_apply": "open", "draft": "open", "new": "open", "backlog": "open", "watching": "open",
    "offen": "open", "gemerkt": "open", "geplant": "open",
    "application_sent": "applied", "submitted": "applied", "application_received": "applied",
    "in_review": "applied", "under_review": "applied", "pending": "applied", "review": "applied",
    "screening": "applied", "phone_screen": "applied", "assessment": "applied",
    "in_progress": "applied", "applying": "applied",
    "beworben": "applied", "eingereicht": "applied", "in_bearbeitung": "applied",
    "interview": "interview_done", "interviewing": "interview_done", "interviewed": "interview_done",
    "interview_scheduled": "interview_done", "onsite": "interview_done", "technical_interview": "interview_done",
    "vorstellungsgespräch": "interview_done", "gespräch": "interview_done", "einladung": "interview_done",
    "declined": "rejected", "not_selected": "rejected", "rejection": "rejected",
    "closed": "rejected", "no": "rejected", "ghosted": "rejected", "withdrawn": "rejected",
    "abgelehnt": "rejected", "absage": "rejected", "zurückgezogen": "rejected",
    "offer": "accepted", "offer_received": "accepted", "hired": "accepted",
    "got_offer": "accepted", "yes": "accepted", "success": "accepted",
    "angenommen": "accepted", "zusage": "accepted", "eingestellt": "accepted",
}


def _norm_key(k: str) -> str:
    return re.sub(r"[\s\-]+", "_", (k or "").strip().lower())


def _canonicalize(rec: dict) -> dict:
    """Remap a record's keys (case/alias-insensitive) onto our job field names."""
    out: dict = {}
    for k, v in rec.items():
        canon = _ALIAS_TO_FIELD.get(_norm_key(k))
        if canon and canon not in out:
            out[canon] = v
    return out


def _normalize_status(value: str) -> str:
    key = _norm_key(value)
    if key in VALID_STATUSES:
        return key
    return _STATUS_SYNONYMS.get(key, "open")


def _normalize_job_type(value: str) -> str:
    """Map an imported employment-type string (EN/DE) to a canonical bucket."""
    t = (value or "").strip().lower()
    if not t:
        return ""
    if any(k in t for k in ("intern", "praktik", "werkstud")):
        return "internship"
    if any(k in t for k in ("freelance", "freiberuf")):
        return "freelance"
    if any(k in t for k in ("contract", "fixed-term", "temporary")) or \
            ("befristet" in t and "unbefristet" not in t):
        return "contract"
    if any(k in t for k in ("mini-job", "mini job", "minijob", "marginal", "geringfügig", "geringfugig")):
        return "mini-job"
    if any(k in t for k in ("part", "teilzeit")):
        return "part-time"
    if any(k in t for k in ("full", "vollzeit", "permanent", "unbefristet")):
        return "full-time"
    return t  # keep unrecognized values as-is rather than dropping data


def _normalize_work_mode(value: str) -> str:
    """Map an imported work-arrangement string (EN/DE) to remote/hybrid/on-site."""
    t = (value or "").strip().lower()
    if not t:
        return ""
    if "hybrid" in t:
        return "hybrid"
    if any(k in t for k in ("remote", "home office", "homeoffice", "work from home", "telearbeit", "fernarbeit")):
        return "remote"
    if any(k in t for k in ("on-site", "on site", "onsite", "office", "vor ort", "präsenz", "praesenz")):
        return "on-site"
    return t  # keep unrecognized values as-is rather than dropping data


def _first_error(exc: ValidationError) -> str:
    err = exc.errors()[0]
    loc = ".".join(str(x) for x in err.get("loc", ()) if x != "__root__")
    msg = err.get("msg", "invalid value")
    return f"{loc}: {msg}" if loc else msg


def _parse_records(text: str, filename: str) -> list[dict]:
    """Turn an uploaded CSV or JSON payload into a list of raw job dicts."""
    stripped = text.lstrip()
    is_json = filename.lower().endswith(".json") or stripped[:1] in ("[", "{")
    if is_json:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise HTTPException(400, f"Invalid JSON: {e}")
        if isinstance(data, dict):
            data = data.get("jobs", [data])
        if not isinstance(data, list):
            raise HTTPException(400, "JSON must be a list of jobs or an object with a 'jobs' list")
        return data
    # CSV (DictReader handles the header row; extra columns like id are ignored)
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)

@router.get("/api/jobs", response_model=list[Job])
def list_jobs():
    return db.list_jobs()


@router.get("/api/jobs/{job_id}", response_model=Job)
def get_job(job_id: int):
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/api/jobs", response_model=Job, status_code=201)
def create_job(payload: JobInput):
    return db.create_job(payload.model_dump())


@router.post("/api/jobs/import")
async def import_jobs(file: UploadFile = File(...)):
    """Bulk-import jobs from a CSV or JSON file.

    Unknown columns/keys (id, created_at, …) are ignored. Position and company
    are required; a missing date_applied defaults to today and a missing status
    to "open". Rows duplicating an existing job (same position+company+date) are
    skipped. Returns per-row errors instead of failing the whole import.
    """
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")

    records = _parse_records(text, file.filename or "")

    # Snapshot existing jobs for duplicate detection.
    existing = {
        (
            (j.get("position") or "").strip().lower(),
            (j.get("company") or "").strip().lower(),
            (j.get("date_applied") or "").strip(),
        )
        for j in db.list_jobs()
    }
    seen: set = set()

    imported = 0
    skipped = 0
    errors: list[dict] = []

    for i, rec in enumerate(records, start=1):
        if not isinstance(rec, dict):
            errors.append({"row": i, "error": "row is not an object"})
            continue
        # Skip entirely blank rows (e.g. trailing CSV newlines) without noise.
        if not any(str(v).strip() for v in rec.values() if v is not None):
            continue
        canon = _canonicalize(rec)
        clean = {
            k: ("" if canon.get(k) is None else str(canon.get(k)).strip())
            for k in _JOB_FIELDS
            if k in canon
        }
        if not clean.get("date_applied"):
            clean["date_applied"] = date.today().isoformat()
        clean["status"] = _normalize_status(clean.get("status"))
        if clean.get("job_type"):
            clean["job_type"] = _normalize_job_type(clean["job_type"])
        if clean.get("work_mode"):
            clean["work_mode"] = _normalize_work_mode(clean["work_mode"])
        try:
            job = JobInput(**clean)
        except ValidationError as e:
            errors.append({"row": i, "error": _first_error(e)})
            continue

        key = (job.position.strip().lower(), job.company.strip().lower(), job.date_applied.strip())
        if key in existing or key in seen:
            skipped += 1
            continue
        seen.add(key)
        db.create_job(job.model_dump())
        imported += 1

    return {"total": len(records), "imported": imported, "skipped": skipped, "errors": errors}


@router.put("/api/jobs/{job_id}", response_model=Job)
def update_job(job_id: int, payload: JobInput):
    if db.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return db.update_job(job_id, payload.model_dump())


@router.delete("/api/jobs/{job_id}")
def delete_job(job_id: int):
    if not db.delete_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return {"deleted": True}

