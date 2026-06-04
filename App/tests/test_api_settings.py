def test_get_settings_returns_defaults(client):
    r = client.get("/api/settings")
    assert r.status_code == 200
    data = r.json()
    assert data["provider"] == "ollama"
    assert data["model"] == "llama3.1:8b"
    assert "providers" in data
    assert set(data["providers"]) == {"ollama", "anthropic", "openai"}
    assert "key_status" in data


def test_key_status_structure(client):
    data = client.get("/api/settings").json()
    ks = data["key_status"]
    assert ks["ollama"] is None       # no key needed
    assert isinstance(ks["anthropic"], bool)
    assert isinstance(ks["openai"], bool)


def test_update_settings_valid(client):
    r = client.put("/api/settings", json={"provider": "ollama", "model": "llama3.2:3b"})
    assert r.status_code == 200
    data = r.json()
    assert data["provider"] == "ollama"
    assert data["model"] == "llama3.2:3b"


def test_update_settings_persists(client):
    client.put("/api/settings", json={"provider": "anthropic", "model": "claude-haiku-4-5"})
    r = client.get("/api/settings")
    assert r.json()["provider"] == "anthropic"
    assert r.json()["model"] == "claude-haiku-4-5"


def test_update_settings_invalid_provider(client):
    r = client.put("/api/settings", json={"provider": "unknown_llm", "model": "gpt-4"})
    assert r.status_code == 422


def test_update_settings_missing_field(client):
    r = client.put("/api/settings", json={"provider": "ollama"})
    assert r.status_code == 422


def test_settings_includes_default_page_size(client):
    assert client.get("/api/settings").json()["page_size"] == 25


def test_update_page_size_round_trips(client):
    r = client.put("/api/settings", json={"provider": "ollama", "model": "llama3.1:8b", "page_size": 75})
    assert r.status_code == 200
    assert r.json()["page_size"] == 75
    assert client.get("/api/settings").json()["page_size"] == 75


def test_update_page_size_is_clamped(client):
    too_big = client.put("/api/settings", json={"provider": "ollama", "model": "llama3.1:8b", "page_size": 99999})
    assert too_big.json()["page_size"] == 500
    too_small = client.put("/api/settings", json={"provider": "ollama", "model": "llama3.1:8b", "page_size": 1})
    assert too_small.json()["page_size"] == 5


def test_update_without_page_size_preserves_it(client):
    client.put("/api/settings", json={"provider": "ollama", "model": "llama3.1:8b", "page_size": 200})
    client.put("/api/settings", json={"provider": "openai", "model": "gpt-4o"})
    assert client.get("/api/settings").json()["page_size"] == 200


def test_get_email_settings(client):
    r = client.get("/api/email/settings")
    assert r.status_code == 200
    data = r.json()
    assert "email_provider" in data
    assert "email_ollama_model" in data
    assert "email_sync_interval" in data


def test_update_email_settings(client):
    r = client.put(
        "/api/email/settings",
        json={"email_ollama_model": "gemma2:2b", "email_sync_interval": 15},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["email_ollama_model"] == "gemma2:2b"
    assert data["email_sync_interval"] == 15
