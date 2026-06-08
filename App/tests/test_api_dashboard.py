def _make(client, position, company, date_applied, status="applied"):
    return client.post("/api/jobs", json={
        "position": position, "company": company,
        "date_applied": date_applied, "status": status,
    }).json()


def test_recent_empty(client):
    data = client.get("/api/dashboard").json()
    assert data["recent"] == []


def test_recent_ordered_by_date_desc(client):
    _make(client, "Old role", "A", "2026-01-01")
    _make(client, "New role", "B", "2026-03-01")
    _make(client, "Mid role", "C", "2026-02-01")

    recent = client.get("/api/dashboard").json()["recent"]
    assert [j["position"] for j in recent] == ["New role", "Mid role", "Old role"]
    # Each row carries what the dashboard card needs.
    assert set(recent[0]) >= {"id", "position", "company", "status", "date_applied", "city"}


def test_recent_capped_at_six(client):
    for i in range(8):
        _make(client, f"Role {i}", "Acme", f"2026-01-0{i + 1}")
    recent = client.get("/api/dashboard").json()["recent"]
    assert len(recent) == 6
    assert recent[0]["position"] == "Role 7"  # most recent first


def test_recent_same_date_breaks_ties_by_newest_id(client):
    a = _make(client, "First", "A", "2026-05-05")
    b = _make(client, "Second", "B", "2026-05-05")
    recent = client.get("/api/dashboard").json()["recent"]
    assert [j["id"] for j in recent[:2]] == [b["id"], a["id"]]
