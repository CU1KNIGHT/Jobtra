import settings as app_settings
from providers import get_provider
from providers.ollama import OllamaProvider, OLLAMA_URL


# ── settings persistence ─────────────────────────────────────────────────────

def test_defaults_when_unset():
    s = app_settings.get_settings()
    assert s["ollama_url"] == OLLAMA_URL
    assert s["lmstudio_url"] == app_settings.DEFAULT_LMSTUDIO_URL


def test_persist_local_urls():
    app_settings.update_settings(
        "ollama", "m", ollama_url="http://box:11434", lmstudio_url="http://box:1234"
    )
    s = app_settings.get_settings()
    assert s["ollama_url"] == "http://box:11434"
    assert s["lmstudio_url"] == "http://box:1234"


def test_blank_url_falls_back_to_default():
    app_settings.update_settings("ollama", "m", ollama_url="   ")
    assert app_settings.get_settings()["ollama_url"] == OLLAMA_URL


def test_url_unchanged_when_not_provided():
    app_settings.update_settings("ollama", "m", ollama_url="http://saved:1")
    app_settings.update_settings("openai", "gpt-4o")  # no url args
    assert app_settings.get_settings()["ollama_url"] == "http://saved:1"


# ── provider construction ────────────────────────────────────────────────────

def test_get_provider_uses_configured_url():
    app_settings.update_settings("ollama", "m", ollama_url="http://remote:9999")
    assert get_provider("ollama").base_url == "http://remote:9999"

    app_settings.update_settings("lmstudio", "m", lmstudio_url="http://remote:1234")
    assert get_provider("lmstudio").api_base == "http://remote:1234"


def test_get_provider_explicit_url_overrides_settings():
    app_settings.update_settings("ollama", "m", ollama_url="http://stored:1")
    assert get_provider("ollama", base_url="http://explicit:2").base_url == "http://explicit:2"


def test_ollama_default_and_trailing_slash_stripped():
    assert OllamaProvider().base_url == OLLAMA_URL
    assert OllamaProvider(base_url="http://x:1/").base_url == "http://x:1"


# ── API surface ──────────────────────────────────────────────────────────────

def test_api_settings_returns_urls(client):
    data = client.get("/api/settings").json()
    assert data["ollama_url"] == OLLAMA_URL
    assert data["lmstudio_url"] == app_settings.DEFAULT_LMSTUDIO_URL


def test_api_put_persists_url(client):
    r = client.put("/api/settings",
                   json={"provider": "ollama", "model": "m", "ollama_url": "http://h:1"})
    assert r.status_code == 200
    assert r.json()["ollama_url"] == "http://h:1"


def test_models_endpoint_threads_url_through(client, monkeypatch):
    import routers.api.models as models_router
    captured = {}

    class _Fake:
        async def list_models(self):
            return ["m1"]

    def fake_get_provider(name, base_url=None):
        captured["name"], captured["url"] = name, base_url
        return _Fake()

    monkeypatch.setattr(models_router, "get_provider", fake_get_provider)
    r = client.get("/api/models?provider=ollama&url=http://custom:1")
    assert r.status_code == 200
    assert captured == {"name": "ollama", "url": "http://custom:1"}
