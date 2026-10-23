"""REST API endpoint tests (FastAPI TestClient)."""
from datetime import datetime, timedelta

import pytest


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_create_and_list_tasks(client):
    res = client.post(
        "/api/tasks",
        json={"title": "API task", "priority": "high", "duration_minutes": 40,
              "deadline": (datetime.now() + timedelta(days=1)).isoformat()},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["title"] == "API task"
    assert body["status"] == "todo"

    res = client.get("/api/tasks")
    assert res.status_code == 200
    assert any(t["id"] == body["id"] for t in res.json())


def test_create_validation_errors(client):
    res = client.post("/api/tasks", json={"title": ""})
    assert res.status_code == 422
    res = client.post("/api/tasks", json={"title": "x", "duration_minutes": 2})
    assert res.status_code == 422
    res = client.post("/api/tasks", json={"title": "x", "priority": "urgent"})
    assert res.status_code == 422


def test_get_missing_task_404(client):
    assert client.get("/api/tasks/nope").status_code == 404


def test_complete_flow_and_persistence(client):
    t = client.post("/api/tasks", json={"title": "To complete"}).json()
    res = client.post(f"/api/tasks/{t['id']}/complete")
    assert res.status_code == 200
    assert res.json()["status"] == "done"
    # Persisted?
    assert client.get(f"/api/tasks/{t['id']}").json()["status"] == "done"


def test_complete_missing_404(client):
    assert client.post("/api/tasks/nope/complete").status_code == 404


def test_delete_flow(client):
    t = client.post("/api/tasks", json={"title": "To delete"}).json()
    res = client.delete(f"/api/tasks/{t['id']}")
    assert res.status_code == 200
    assert res.json()["deleted"] is True
    assert client.get(f"/api/tasks/{t['id']}").status_code == 404
    # Deleting again -> 404
    assert client.delete(f"/api/tasks/{t['id']}").status_code == 404


def test_reschedule_requires_something(client):
    t = client.post("/api/tasks", json={"title": "R"}).json()
    res = client.post(f"/api/tasks/{t['id']}/reschedule", json={})
    assert res.status_code == 422


def test_reschedule_updates_deadline(client):
    t = client.post("/api/tasks", json={"title": "R"}).json()
    new_dl = (datetime.now() + timedelta(days=3)).replace(microsecond=0).isoformat()
    res = client.post(f"/api/tasks/{t['id']}/reschedule", json={"new_deadline": new_dl})
    assert res.status_code == 200
    assert res.json()["task"]["deadline"].startswith(new_dl[:16])
    assert res.json()["changes"]


def test_generate_schedule_endpoint(client):
    client.post("/api/tasks", json={"title": "S1", "duration_minutes": 30,
                                    "deadline": (datetime.now() + timedelta(hours=4)).isoformat()})
    res = client.post("/api/schedule/generate", json={})
    assert res.status_code == 200
    body = res.json()
    assert body["scheduled_count"] >= 1
    assert body["explanations"]

    sched = client.get("/api/schedule?days=7").json()
    assert len(sched["blocks"]) >= 1


def test_replan_endpoint(client):
    past = (datetime.now() - timedelta(hours=1)).replace(microsecond=0).isoformat()
    client.post("/api/tasks", json={"title": "Overdue one", "deadline": past})
    res = client.post("/api/schedule/replan", json={})
    assert res.status_code == 200
    body = res.json()
    assert body["replanned"] is True
    assert body["missed_count"] == 1
    assert body["changes"]


def test_progress_endpoint(seeded_client):
    res = seeded_client.get("/api/progress")
    assert res.status_code == 200
    p = res.json()
    assert p["total_tasks"] > 0
    assert p["done"] > 0
    assert 0 <= p["completion_rate"] <= 100


def test_cors_headers_present(client):
    res = client.options(
        "/api/tasks",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_allows_lan_ip_origin(client):
    origin = "http://10.10.34.154:3001"
    res = client.options(
        "/api/tasks",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == origin


def test_cors_rejects_untrusted_origin(client):
    res = client.options(
        "/api/tasks",
        headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "GET"},
    )
    assert res.status_code == 400
