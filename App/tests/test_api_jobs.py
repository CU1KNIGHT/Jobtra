def test_list_jobs_empty(client):
    r = client.get("/api/jobs")
    assert r.status_code == 200
    assert r.json() == []


def test_create_job(client, job_payload):
    r = client.post("/api/jobs", json=job_payload)
    assert r.status_code == 201
    data = r.json()
    assert data["position"] == "Backend Engineer"
    assert data["company"] == "Acme Corp"
    assert "id" in data
    assert "created_at" in data


def test_create_job_missing_required_fields(client):
    r = client.post("/api/jobs", json={"company": "X", "date_applied": "2026-01-01"})
    assert r.status_code == 422


def test_create_job_empty_required_field(client, job_payload):
    r = client.post("/api/jobs", json={**job_payload, "position": ""})
    assert r.status_code == 422


def test_create_job_invalid_status(client, job_payload):
    r = client.post("/api/jobs", json={**job_payload, "status": "flying_high"})
    assert r.status_code == 422


def test_get_job(client, job_payload):
    created = client.post("/api/jobs", json=job_payload).json()
    r = client.get(f"/api/jobs/{created['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]
    assert r.json()["company"] == "Acme Corp"


def test_get_job_not_found(client):
    r = client.get("/api/jobs/9999")
    assert r.status_code == 404


def test_list_jobs_after_create(client, job_payload):
    client.post("/api/jobs", json=job_payload)
    client.post("/api/jobs", json={**job_payload, "company": "Beta Inc"})
    r = client.get("/api/jobs")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_update_job(client, job_payload):
    created = client.post("/api/jobs", json=job_payload).json()
    r = client.put(
        f"/api/jobs/{created['id']}",
        json={**job_payload, "position": "Senior Engineer", "status": "applied"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["position"] == "Senior Engineer"
    assert data["status"] == "applied"


def test_update_job_not_found(client, job_payload):
    r = client.put("/api/jobs/9999", json=job_payload)
    assert r.status_code == 404


def test_delete_job(client, job_payload):
    created = client.post("/api/jobs", json=job_payload).json()
    r = client.delete(f"/api/jobs/{created['id']}")
    assert r.status_code == 200
    assert r.json()["deleted"] is True
    assert client.get(f"/api/jobs/{created['id']}").status_code == 404


def test_delete_job_not_found(client):
    r = client.delete("/api/jobs/9999")
    assert r.status_code == 404


def test_job_appears_in_list_after_create(client, job_payload):
    created = client.post("/api/jobs", json=job_payload).json()
    jobs = client.get("/api/jobs").json()
    ids = [j["id"] for j in jobs]
    assert created["id"] in ids
