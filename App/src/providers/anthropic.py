import json
import os
import httpx
from .base import (
    EXTRACTION_PROMPT, normalize_result,
    ProviderAuthError, ProviderBadOutput, ProviderTimeout, ProviderUnavailable,
)

ANTHROPIC_API_URL = "https://api.anthropic.com"


class AnthropicProvider:
    name = "anthropic"

    def _key(self) -> str:
        key = os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            raise ProviderAuthError("Missing ANTHROPIC_API_KEY")
        return key

    async def parse(self, text: str, model: str) -> dict:
        key = self._key()
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{ANTHROPIC_API_URL}/v1/messages",
                    headers={
                        "x-api-key": key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": model,
                        "max_tokens": 1024,
                        "system": EXTRACTION_PROMPT + "\nRespond with JSON only.",
                        "messages": [{"role": "user", "content": f"Job posting:\n<<<\n{text}\n>>>"}],
                    },
                )
        except httpx.TimeoutException:
            raise ProviderTimeout("Anthropic API timed out")
        except httpx.ConnectError:
            raise ProviderUnavailable("Cannot connect to Anthropic API")

        if resp.status_code in (401, 403):
            raise ProviderAuthError("Invalid or missing Anthropic API key")

        try:
            raw = resp.json()["content"][0]["text"]
            parsed = json.loads(raw)
        except (KeyError, IndexError, json.JSONDecodeError, ValueError):
            raise ProviderBadOutput("Model returned unparseable JSON")

        return normalize_result(parsed)

    async def complete(self, system: str, user: str, model: str) -> str:
        key = self._key()
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{ANTHROPIC_API_URL}/v1/messages",
                    headers={
                        "x-api-key": key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": model,
                        "max_tokens": 1024,
                        "system": system,
                        "messages": [{"role": "user", "content": user}],
                    },
                )
        except httpx.TimeoutException:
            raise ProviderTimeout("Anthropic API timed out")
        except httpx.ConnectError:
            raise ProviderUnavailable("Cannot connect to Anthropic API")
        if resp.status_code in (401, 403):
            raise ProviderAuthError("Invalid or missing Anthropic API key")
        try:
            return resp.json()["content"][0]["text"]
        except (KeyError, IndexError, ValueError):
            raise ProviderBadOutput("Unexpected response from Anthropic")

    async def list_models(self) -> list[str]:
        key = self._key()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{ANTHROPIC_API_URL}/v1/models",
                    headers={
                        "x-api-key": key,
                        "anthropic-version": "2023-06-01",
                    },
                )
        except httpx.ConnectError:
            raise ProviderUnavailable("Cannot reach Anthropic API")
        except httpx.TimeoutException:
            raise ProviderUnavailable("Anthropic API timed out")

        if resp.status_code in (401, 403):
            raise ProviderAuthError("Invalid or missing Anthropic API key")

        try:
            models = resp.json().get("data", [])
            return [m["id"] for m in models if "claude" in m.get("id", "").lower()]
        except Exception:
            raise ProviderBadOutput("Unexpected response from Anthropic")
