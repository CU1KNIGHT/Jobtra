from datetime import date
from typing import Protocol, runtime_checkable

EXTRACTION_PROMPT = """\
You are a job-posting parser. Extract structured data from the job
posting below and return ONLY a JSON object with these fields:

  position       string  - job title
  company        string  - company name
  description    string  - the full job description / main body text, copied verbatim from the posting (not a summary)
  city           string  - city or cities where the job is located, comma-separated if multiple, "" if fully remote or unknown
  address        string  - full street address if present, else ""
  hr_email       string  - contact email if present, else ""
  hr_phone       string  - contact phone number if present, else ""
  whatsapp       string  - WhatsApp number or link if explicitly mentioned, else ""
  telegram       string  - Telegram username or link if explicitly mentioned, else ""
  hours_per_week string  - weekly hours (e.g. "40", "20-30", "part-time"), "" if not mentioned
  languages      string  - required languages comma-separated; list English first if present, else in order found; "" if none mentioned
  skills         string  - comma-separated list of required technical skills

If a field is not present in the text, use an empty string. Do not
invent information. Output JSON only, no commentary."""

EXPECTED_KEYS = frozenset(
    {"position", "company", "description", "city", "address",
     "hr_email", "hr_phone", "whatsapp", "telegram",
     "hours_per_week", "languages", "skills"}
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
    async def complete(self, system: str, user: str, model: str) -> str: ...
