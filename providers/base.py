from datetime import date
from typing import Protocol, runtime_checkable

EXTRACTION_PROMPT = """\
You are a job-posting parser. Extract structured data from the job
posting below and return ONLY a JSON object with these fields:

  position      string  - job title
  company       string  - company name
  description   string  - 1-2 sentence summary of the role
  city          string  - city where the job is located, "" if remote/unknown
  address       string  - full street address if present, else ""
  hr_email      string  - contact email if present, else ""
  hr_phone      string  - contact phone if present, else ""
  skills        string  - comma-separated list of required technical skills

If a field is not present in the text, use an empty string. Do not
invent information. Output JSON only, no commentary."""

EXPECTED_KEYS = frozenset(
    {"position", "company", "description", "city", "address", "hr_email", "hr_phone", "skills"}
)


class ProviderError(Exception): ...
class ProviderUnavailable(ProviderError): ...
class ProviderAuthError(ProviderError): ...
class ProviderBadOutput(ProviderError): ...
class ProviderTimeout(ProviderError): ...


def normalize_result(parsed: dict) -> dict:
    result = {k: str(parsed.get(k, "")) for k in EXPECTED_KEYS}
    result["date_applied"] = date.today().isoformat()
    result["status"] = "open"
    return result


@runtime_checkable
class Provider(Protocol):
    name: str

    async def parse(self, text: str, model: str) -> dict: ...
    async def list_models(self) -> list[str]: ...
