import json
import os
from datetime import date

import httpx

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4")

_PROMPT = """\
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
invent information. Output JSON only, no commentary.

Job posting:
<<<
{user_text}
>>>"""

_EXPECTED = {"position", "company", "description", "city", "address", "hr_email", "hr_phone", "skills"}


class ParserUnavailable(Exception):
    def __init__(self, msg: str, model: str | None = None):
        super().__init__(msg)
        self.model = model


class ParserTimeout(Exception):
    pass


class ParserBadOutput(Exception):
    pass


async def parse_job_description(text: str) -> dict:
    prompt = _PROMPT.format(user_text=text)
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.1},
                },
            )
    except httpx.ConnectError:
        raise ParserUnavailable("connection refused")
    except httpx.TimeoutException:
        raise ParserTimeout("ollama timed out")

    if resp.status_code == 404:
        raise ParserUnavailable(f"model not found: {OLLAMA_MODEL}", model=OLLAMA_MODEL)

    try:
        raw = resp.json()["response"]
        parsed = json.loads(raw)
    except (KeyError, json.JSONDecodeError, ValueError):
        raise ParserBadOutput("model returned unparseable JSON")

    result = {k: str(parsed.get(k, "")) for k in _EXPECTED}
    result["date_applied"] = date.today().isoformat()
    result["status"] = "open"
    return result
