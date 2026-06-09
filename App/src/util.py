from pydantic import BaseModel, field_validator

VALID_STATUSES = {"open", "applied", "interview_invite", "interview_done", "rejected", "rejected_after_interview", "accepted"}
VALID_PROVIDERS = ["ollama", "lmstudio", "anthropic", "openai"]

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
    whatsapp: str = ""
    telegram: str = ""
    hours_per_week: str = ""
    languages: str = ""
    job_type: str = ""
    work_mode: str = ""
    skills: str = ""
    source_url: str = ""
    source_text: str = ""

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