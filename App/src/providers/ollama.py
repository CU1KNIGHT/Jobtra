import json
import httpx
from .base import (
    EXTRACTION_PROMPT, normalize_result,
    ProviderUnavailable, ProviderBadOutput, ProviderTimeout,
)

OLLAMA_URL = "http://localhost:11434"


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str = None):
        self.base_url = (base_url or "").rstrip("/") or OLLAMA_URL

    async def parse(self, text: str, model: str) -> dict:
        prompt = EXTRACTION_PROMPT + f"\n\nJob posting:\n<<<\n{text}\n>>>"
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                        "options": {"temperature": 0.1},
                    },
                )
        except httpx.ConnectError:
            raise ProviderUnavailable("Ollama is not running")
        except httpx.TimeoutException:
            raise ProviderTimeout("Ollama timed out")

        if resp.status_code == 404:
            raise ProviderUnavailable(f"Model '{model}' not found. Pull it with: ollama pull {model}")

        try:
            raw = resp.json()["response"]
            parsed = json.loads(raw)
        except (KeyError, json.JSONDecodeError, ValueError):
            raise ProviderBadOutput("Model returned unparseable JSON")

        return normalize_result(parsed)

    async def complete(self, system: str, user: str, model: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "stream": False,
                        "format": "json",
                        "options": {"temperature": 0.1},
                    },
                )
        except httpx.ConnectError:
            raise ProviderUnavailable("Ollama is not running")
        except httpx.TimeoutException:
            raise ProviderTimeout("Ollama timed out")
        if resp.status_code == 404:
            raise ProviderUnavailable(f"Model '{model}' not found. Pull it with: ollama pull {model}")
        try:
            return resp.json()["message"]["content"]
        except (KeyError, ValueError):
            raise ProviderBadOutput("Unexpected response from Ollama")

    async def list_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
        except httpx.ConnectError:
            raise ProviderUnavailable("Ollama is not running")
        except httpx.TimeoutException:
            raise ProviderUnavailable("Ollama timed out")

        try:
            return [m["name"] for m in resp.json().get("models", [])]
        except Exception:
            raise ProviderUnavailable("Unexpected response from Ollama")
