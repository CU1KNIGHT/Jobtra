import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from providers.ollama import OllamaProvider
from providers.anthropic import AnthropicProvider
from providers.openai import OpenAIProvider
from providers.base import ProviderUnavailable, ProviderAuthError, ProviderBadOutput, ProviderTimeout


def _ctx(mock_client):
    """Wrap a mock client in an async context manager."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _resp(status=200, body=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = body or {}
    return r


# ── OllamaProvider ─────────────────────────────────────────────────────────────

async def test_ollama_complete_success():
    mc = AsyncMock()
    mc.post.return_value = _resp(200, {"message": {"content": '{"ok": true}'}})

    with patch("httpx.AsyncClient", return_value=_ctx(mc)):
        result = await OllamaProvider().complete("sys", "user", "llama3.1:8b")

    assert result == '{"ok": true}'


async def test_ollama_complete_connect_error():
    mc = AsyncMock()
    mc.post.side_effect = httpx.ConnectError("refused")

    with patch("httpx.AsyncClient", return_value=_ctx(mc)):
        with pytest.raises(ProviderUnavailable, match="not running"):
            await OllamaProvider().complete("sys", "user", "llama3.1:8b")


async def test_ollama_complete_timeout():
    mc = AsyncMock()
    mc.post.side_effect = httpx.TimeoutException("timeout")

    with patch("httpx.AsyncClient", return_value=_ctx(mc)):
        with pytest.raises(ProviderTimeout):
            await OllamaProvider().complete("sys", "user", "llama3.1:8b")


async def test_ollama_complete_model_not_found():
    mc = AsyncMock()
    mc.post.return_value = _resp(404)

    with patch("httpx.AsyncClient", return_value=_ctx(mc)):
        with pytest.raises(ProviderUnavailable, match="not found"):
            await OllamaProvider().complete("sys", "user", "no-model")


async def test_ollama_list_models():
    mc = AsyncMock()
    mc.get.return_value = _resp(200, {"models": [{"name": "llama3.1:8b"}, {"name": "gemma2:2b"}]})

    with patch("httpx.AsyncClient", return_value=_ctx(mc)):
        models = await OllamaProvider().list_models()

    assert "llama3.1:8b" in models
    assert "gemma2:2b" in models


async def test_ollama_list_models_not_running():
    mc = AsyncMock()
    mc.get.side_effect = httpx.ConnectError("refused")

    with patch("httpx.AsyncClient", return_value=_ctx(mc)):
        with pytest.raises(ProviderUnavailable):
            await OllamaProvider().list_models()


# ── AnthropicProvider ──────────────────────────────────────────────────────────

async def test_anthropic_complete_success(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    mc = AsyncMock()
    mc.post.return_value = _resp(200, {"content": [{"text": '{"status": "ok"}'}]})

    with patch("httpx.AsyncClient", return_value=_ctx(mc)):
        result = await AnthropicProvider().complete("sys", "user", "claude-haiku-4-5")

    assert result == '{"status": "ok"}'


async def test_anthropic_complete_missing_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ProviderAuthError, match="ANTHROPIC_API_KEY"):
        await AnthropicProvider().complete("sys", "user", "claude-haiku-4-5")


async def test_anthropic_complete_invalid_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "bad-key")
    mc = AsyncMock()
    mc.post.return_value = _resp(401)

    with patch("httpx.AsyncClient", return_value=_ctx(mc)):
        with pytest.raises(ProviderAuthError):
            await AnthropicProvider().complete("sys", "user", "claude-haiku-4-5")


async def test_anthropic_list_models(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    mc = AsyncMock()
    mc.get.return_value = _resp(200, {
        "data": [{"id": "claude-sonnet-4-6"}, {"id": "claude-haiku-4-5"}, {"id": "other-model"}]
    })

    with patch("httpx.AsyncClient", return_value=_ctx(mc)):
        models = await AnthropicProvider().list_models()

    assert "claude-sonnet-4-6" in models
    assert "claude-haiku-4-5" in models
    assert "other-model" not in models  # filtered out (no "claude" in name)


# ── OpenAIProvider ─────────────────────────────────────────────────────────────

async def test_openai_complete_success(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    mc = AsyncMock()
    mc.post.return_value = _resp(200, {"choices": [{"message": {"content": '{"result": 1}'}}]})

    with patch("httpx.AsyncClient", return_value=_ctx(mc)):
        result = await OpenAIProvider().complete("sys", "user", "gpt-4o")

    assert result == '{"result": 1}'


async def test_openai_complete_missing_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ProviderAuthError, match="OPENAI_API_KEY"):
        await OpenAIProvider().complete("sys", "user", "gpt-4o")


async def test_openai_complete_auth_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "bad-key")
    mc = AsyncMock()
    mc.post.return_value = _resp(403)

    with patch("httpx.AsyncClient", return_value=_ctx(mc)):
        with pytest.raises(ProviderAuthError):
            await OpenAIProvider().complete("sys", "user", "gpt-4o")


async def test_openai_list_models(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    mc = AsyncMock()
    mc.get.return_value = _resp(200, {
        "data": [{"id": "gpt-4o"}, {"id": "gpt-4o-mini"}, {"id": "whisper-1"}]
    })

    with patch("httpx.AsyncClient", return_value=_ctx(mc)):
        models = await OpenAIProvider().list_models()

    assert "gpt-4o" in models
    assert "gpt-4o-mini" in models
    assert "whisper-1" not in models  # filtered: must start with "gpt-"
