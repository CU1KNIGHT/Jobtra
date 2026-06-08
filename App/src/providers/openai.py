import json
import os
import httpx
from .base import (
    EXTRACTION_PROMPT, normalize_result,
    ProviderAuthError, ProviderBadOutput, ProviderTimeout, ProviderUnavailable,
)


class OpenAIProvider:
    """OpenAI Chat Completions provider.

    The request/response shape is the de-facto standard implemented by many
    other services (OpenRouter, Groq, LM Studio, vLLM, …), so this class is also
    the base for any OpenAI-compatible endpoint — subclasses just override the
    base URL, label, API-key source, and model filter.
    """
    name = "openai"
    label = "OpenAI"
    api_base = "https://api.openai.com"   # root; "/v1/..." is appended
    api_key_env = "OPENAI_API_KEY"
    model_prefix = "gpt-"                  # None = list every model unfiltered

    def _key(self) -> str:
        key = os.getenv(self.api_key_env, "")
        if not key:
            raise ProviderAuthError(f"Missing {self.api_key_env}")
        return key

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._key()}",
            "content-type": "application/json",
        }

    async def parse(self, text: str, model: str) -> dict:
        headers = self._headers()
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self.api_base}/v1/chat/completions",
                    headers=headers,
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
            raise ProviderTimeout(f"{self.label} API timed out")
        except httpx.ConnectError:
            raise ProviderUnavailable(f"Cannot connect to {self.label}")

        if resp.status_code in (401, 403):
            raise ProviderAuthError(f"Invalid or missing {self.label} API key")

        try:
            raw = resp.json()["choices"][0]["message"]["content"]
            parsed = json.loads(raw)
        except (KeyError, IndexError, json.JSONDecodeError, ValueError):
            raise ProviderBadOutput("Model returned unparseable JSON")

        return normalize_result(parsed)

    async def complete(self, system: str, user: str, model: str) -> str:
        headers = self._headers()
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self.api_base}/v1/chat/completions",
                    headers=headers,
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
            raise ProviderTimeout(f"{self.label} API timed out")
        except httpx.ConnectError:
            raise ProviderUnavailable(f"Cannot connect to {self.label}")
        if resp.status_code in (401, 403):
            raise ProviderAuthError(f"Invalid or missing {self.label} API key")
        try:
            return resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError):
            raise ProviderBadOutput(f"Unexpected response from {self.label}")

    async def list_models(self) -> list[str]:
        headers = self._headers()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.api_base}/v1/models", headers=headers)
        except httpx.ConnectError:
            raise ProviderUnavailable(f"Cannot reach {self.label}")
        except httpx.TimeoutException:
            raise ProviderUnavailable(f"{self.label} timed out")

        if resp.status_code in (401, 403):
            raise ProviderAuthError(f"Invalid or missing {self.label} API key")

        try:
            ids = [m["id"] for m in resp.json().get("data", []) if m.get("id")]
        except Exception:
            raise ProviderBadOutput(f"Unexpected response from {self.label}")

        if self.model_prefix:
            ids = sorted([i for i in ids if i.startswith(self.model_prefix)], reverse=True)
        return ids
