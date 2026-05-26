from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, field_validator
from dotenv import load_dotenv
import os

import db
import settings as app_settings
from providers import get_provider
from providers.base import (
    ProviderUnavailable, ProviderAuthError, ProviderBadOutput, ProviderTimeout,
)

load_dotenv()

app = FastAPI(title="Job Application Tracker")

VALID_STATUSES = {"open", "applied", "interview_done", "rejected", "rejected_after_interview", "accepted"}
VALID_PROVIDERS = ["ollama", "anthropic", "openai"]


class JobInput(BaseModel):
    position: str
    company: str
    description: str = ""
    date_applied: str
    status: str = "open"
    address: str = ""
    city: str = ""
    hr_email: str = ""
    hr_phone: str = ""
    skills: str = ""

    @field_validator("position", "company", "date_applied")
    @classmethod
    def must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("field is required and must not be empty")
        return v.strip()

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(f"status must be one of {sorted(VALID_STATUSES)}")
        return v


class Job(JobInput):
    id: int
    created_at: str
    updated_at: str


class ParseInput(BaseModel):
    text: str


class SettingsInput(BaseModel):
    provider: str
    model: str


@app.get("/")
def index():
    return FileResponse("index.html")


@app.get("/settings")
def settings_page():
    return FileResponse("settings.html")


@app.get("/api/jobs", response_model=list[Job])
def list_jobs():
    return db.list_jobs()


@app.get("/api/jobs/{job_id}", response_model=Job)
def get_job(job_id: int):
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/api/jobs", response_model=Job, status_code=201)
def create_job(payload: JobInput):
    return db.create_job(payload.model_dump())


@app.put("/api/jobs/{job_id}", response_model=Job)
def update_job(job_id: int, payload: JobInput):
    if db.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return db.update_job(job_id, payload.model_dump())


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: int):
    if not db.delete_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return {"deleted": True}


@app.get("/api/settings")
def get_settings():
    s = app_settings.get_settings()
    key_status = {
        "ollama": None,
        "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
        "openai": bool(os.getenv("OPENAI_API_KEY")),
    }
    return {**s, "providers": VALID_PROVIDERS, "key_status": key_status}


@app.put("/api/settings")
def update_settings(payload: SettingsInput):
    try:
        return app_settings.update_settings(payload.provider, payload.model)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/api/models")
async def list_models(provider: str = Query(...)):
    if provider not in VALID_PROVIDERS:
        raise HTTPException(status_code=422, detail=f"Unknown provider: {provider}")
    try:
        p = get_provider(provider)
        models = await p.list_models()
        return {"models": models}
    except ProviderAuthError as e:
        key_name = "ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY"
        return JSONResponse(
            status_code=401,
            content={"error": str(e), "hint": f"Add {key_name} to .env"},
        )
    except ProviderUnavailable as e:
        return JSONResponse(
            status_code=503,
            content={"error": str(e), "hint": "Start Ollama with: ollama serve"},
        )
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": str(e)})


@app.post("/api/parse")
async def parse_job(payload: ParseInput):
    s = app_settings.get_settings()
    provider_name = s["provider"]
    model = s["model"]

    try:
        p = get_provider(provider_name)
        return await p.parse(payload.text, model)
    except ProviderAuthError as e:
        key_name = "ANTHROPIC_API_KEY" if provider_name == "anthropic" else "OPENAI_API_KEY"
        return JSONResponse(
            status_code=401,
            content={"error": str(e), "hint": f"Add {key_name} to .env"},
        )
    except ProviderUnavailable as e:
        hint = f"Start Ollama with: ollama serve" if provider_name == "ollama" else str(e)
        return JSONResponse(status_code=503, content={"error": str(e), "hint": hint})
    except ProviderBadOutput:
        return JSONResponse(status_code=502, content={"error": "Model returned invalid JSON"})
    except ProviderTimeout:
        return JSONResponse(status_code=504, content={"error": "Provider timed out"})
