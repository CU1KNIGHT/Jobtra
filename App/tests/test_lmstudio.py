import asyncio

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import settings as app_settings
from providers import get_provider
from providers.lmstudio import LMStudioProvider


def _ctx(mock_client):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _resp(status=200, body=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = body or {}
    return r


# ── registry / configuration ────────────────────────────────────────────────

def test_registered_and_local():
    p = get_provider("lmstudio")
    assert isinstance(p, LMStudioProvider)
    assert p.name == "lmstudio"
    assert p.model_prefix is None  # no model filtering for a local server


def test_default_base_url(monkeypatch):
    monkeypatch.delenv("LMSTUDIO_BASE_URL", raising=False)
    assert LMStudioProvider().api_base == "http://localhost:1234"


def test_base_url_override(monkeypatch):
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://10.0.0.5:4321")
    assert LMStudioProvider().api_base == "http://10.0.0.5:4321"


def test_no_auth_header():
    headers = LMStudioProvider()._headers()
    assert "Authorization" not in headers  # local server needs no key


# ── HTTP behaviour (run the async methods via asyncio.run) ───────────────────

def test_list_models_unfiltered_and_unauthenticated():
    mc = AsyncMock()
    mc.get.return_value = _resp(200, {"data": [
        {"id": "qwen2.5-7b-instruct"}, {"id": "whisper-1"}, {"id": "llama-3.2-3b"},
    ]})
    with patch("httpx.AsyncClient", return_value=_ctx(mc)):
        models = asyncio.run(LMStudioProvider().list_models())

    # Every loaded model is returned — no "gpt-" filtering like OpenAI.
    assert set(models) == {"qwen2.5-7b-instruct", "whisper-1", "llama-3.2-3b"}
    # The request carried no Authorization header.
    _, kwargs = mc.get.call_args
    assert "Authorization" not in kwargs["headers"]


def test_complete_hits_lmstudio_endpoint(monkeypatch):
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://localhost:1234")
    mc = AsyncMock()
    mc.post.return_value = _resp(200, {"choices": [{"message": {"content": '{"ok": 1}'}}]})
    with patch("httpx.AsyncClient", return_value=_ctx(mc)):
        out = asyncio.run(LMStudioProvider().complete("sys", "user", "local-model"))

    assert out == '{"ok": 1}'
    assert mc.post.call_args[0][0] == "http://localhost:1234/v1/chat/completions"


# ── settings acceptance ──────────────────────────────────────────────────────

def test_settings_accepts_lmstudio():
    s = app_settings.update_settings("lmstudio", "local-model")
    assert s["provider"] == "lmstudio"
    assert s["model"] == "local-model"


def test_api_settings_exposes_lmstudio(client):
    body = client.get("/api/settings").json()
    assert "lmstudio" in body["providers"]
    assert body["key_status"]["lmstudio"] is None  # no key needed


def test_api_update_settings_lmstudio(client):
    r = client.put("/api/settings", json={"provider": "lmstudio", "model": "local-model"})
    assert r.status_code == 200
    assert r.json()["provider"] == "lmstudio"
