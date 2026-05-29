import json
import os
import httpx
from .base import (
    EXTRACTION_PROMPT, normalize_result,
    ProviderAuthError, ProviderBadOutput, ProviderTimeout, ProviderUnavailable,
)

OPENAI_API_URL = "https://api.openai.com"


class OpenAIProvider:
    name = "openai"

    def _key(self) -> str:
        key = os.getenv("OPENAI_API_KEY", "")
        if not key:
            raise ProviderAuthError("Missing OPENAI_API_KEY")
        return key

    async def parse(self, text: str, model: str) -> dict:
        key = self._key()
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{OPENAI_API_URL}/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "content-type": "application/json",
                    },
                    json={
                        "model": model,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {"role": "system", "content": EXTRACTION_PROMPT},
                            {"role": "user", "content": f"Job posting:\n<<<\n{text}\n>>>"},
                        ],
                        "temperature": 0.1,
                    },
                )
        except httpx.TimeoutException:
            raise ProviderTimeout("OpenAI API timed out")
        except httpx.ConnectError:
            raise ProviderUnavailable("Cannot connect to OpenAI API")

        if resp.status_code in (401, 403):
            raise ProviderAuthError("Invalid or missing OpenAI API key")

        try:
            raw = resp.json()["choices"][0]["message"]["content"]
            parsed = json.loads(raw)
        except (KeyError, IndexError, json.JSONDecodeError, ValueError):
            raise ProviderBadOutput("Model returned unparseable JSON")

        return normalize_result(parsed)

    async def complete(self, system: str, user: str, model: str) -> str:
        key = self._key()
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{OPENAI_API_URL}/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "content-type": "application/json",
                    },
                    json={
                        "model": model,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "temperature": 0.1,
                    },
                )
        except httpx.TimeoutException:
            raise ProviderTimeout("OpenAI API timed out")
        except httpx.ConnectError:
            raise ProviderUnavailable("Cannot connect to OpenAI API")
        if resp.status_code in (401, 403):
            raise ProviderAuthError("Invalid or missing OpenAI API key")
        try:
            return resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError):
            raise ProviderBadOutput("Unexpected response from OpenAI")

    async def list_models(self) -> list[str]:
        key = self._key()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{OPENAI_API_URL}/v1/models",
                    headers={"Authorization": f"Bearer {key}"},
                )
        except httpx.ConnectError:
            raise ProviderUnavailable("Cannot reach OpenAI API")
        except httpx.TimeoutException:
            raise ProviderUnavailable("OpenAI API timed out")

        if resp.status_code in (401, 403):
            raise ProviderAuthError("Invalid or missing OpenAI API key")

        try:
            models = resp.json().get("data", [])
            return sorted(
                [m["id"] for m in models if m.get("id", "").startswith("gpt-")],
                reverse=True,
            )
        except Exception:
            raise ProviderBadOutput("Unexpected response from OpenAI")
