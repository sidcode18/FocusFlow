"""Task service tests: CRUD, verification of mutations, persistence across connections."""
from datetime import datetime, timedelta

import pytest

from app.services import tasks as svc
from app.services.tasks import TaskNotFoundError


def test_create_and_get_roundtrip(clean_db):
    deadline = datetime.now() + timedelta(days=1)
    t = svc.create_task("Write tests", "high", deadline, 45, "pytest")
    got = svc.get_task(t["id"])
    assert got["title"] == "Write tests"
    assert got["priority"] == "high"
    assert got["status"] == "todo"
    assert datetime.fromisoformat(got["deadline"]) == deadline.replace(microsecond=0)
    assert got["duration_minutes"] == 45


def test_complete_persists_and_is_verified(clean_db):
    t = svc.create_task("Ship it", "medium")
    done = svc.complete_task(t["id"])
    assert done["status"] == "done"
    assert done["completed_at"] is not None
    # Re-read via a fresh connection to confirm persistence
    assert svc.get_task(t["id"])["status"] == "done"


def test_delete_cascades_blocks(clean_db):
    from app.db import get_conn
    from app.services.scheduler import generate_schedule

    t = svc.create_task("Doomed task", "low", datetime.now() + timedelta(days=1), 30)
    with get_conn() as conn:
        generate_schedule(conn)
    with get_conn() as conn:
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM schedule_blocks WHERE task_id = ?", (t["id"],)
        ).fetchone()["n"]
    assert n == 1
    svc.delete_task(t["id"])
    with pytest.raises(TaskNotFoundError):
        svc.get_task(t["id"])
    with get_conn() as conn:
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM schedule_blocks WHERE task_id = ?", (t["id"],)
        ).fetchone()["n"]
    assert n == 0, "schedule blocks must cascade on delete"


def test_reschedule_reopens_missed_task(clean_db):
    t = svc.create_task("Missed thing", "medium", datetime.now() - timedelta(hours=3), 30)
    new_deadline = datetime.now() + timedelta(days=1)
    result = svc.reschedule_task(t["id"], new_deadline=new_deadline, reason="user request")
    assert result["task"]["status"] == "todo"
    assert datetime.fromisoformat(result["task"]["deadline"]).replace(microsecond=0) == (
        new_deadline.replace(microsecond=0)
    )
    assert result["changes"], "reschedule must report its changes"


def test_update_task_fields(clean_db):
    t = svc.create_task("Draft", "low")
    updated = svc.update_task(t["id"], {"title": "Final", "priority": "high", "duration_minutes": 90})
    assert updated["title"] == "Final"
    assert updated["priority"] == "high"
    assert updated["duration_minutes"] == 90


def test_persistence_across_service_restarts(clean_db):
    """SQLite durability: data written now must be readable by a later 'process'."""
    t = svc.create_task("Survives restart", "high", datetime.now() + timedelta(days=2), 30)
    svc.complete_task(t["id"])
    # Simulate restart: brand-new reads against the same DB file
    found = [x for x in svc.list_tasks(status="done") if x["id"] == t["id"]]
    assert len(found) == 1
    assert found[0]["title"] == "Survives restart"


def test_missing_task_raises(clean_db):
    with pytest.raises(TaskNotFoundError):
        svc.get_task("nonexistent")
