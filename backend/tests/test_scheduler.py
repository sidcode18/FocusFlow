"""Unit tests for the deterministic scheduler and replanner."""
from datetime import datetime, timedelta

import pytest

from app.db import get_conn
from app.services.scheduler import generate_schedule, replan
from app.services.tasks import create_task


def _blocks_for(conn, task_id):
    return [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM schedule_blocks WHERE task_id = ? ORDER BY start_time", (task_id,)
        ).fetchall()
    ]


def test_schedules_before_deadline_in_work_window(clean_db):
    now = datetime.now()
    t1 = create_task("Urgent report", "high", now + timedelta(hours=6), 60)
    t2 = create_task("Chores", "low", now + timedelta(days=2), 30)
    with get_conn() as conn:
        result = generate_schedule(conn)
    assert result["unscheduled"] == []
    assert len(result["explanations"]) == 2
    with get_conn() as conn:
        b1 = _blocks_for(conn, t1["id"])
    assert b1, "urgent task should have a block"
    start = datetime.fromisoformat(b1[0]["start_time"])
    end = datetime.fromisoformat(b1[0]["end_time"])
    assert (end - start).total_seconds() / 60 == 60
    assert start.hour >= 9 and end.hour <= 18 or end.hour == 18
    assert start <= datetime.fromisoformat(t1["deadline"]) or end <= datetime.fromisoformat(
        t1["deadline"]
    )
    with get_conn() as conn:
        b2 = _blocks_for(conn, t2["id"])
    assert b2, "low priority task should also be scheduled"


def test_earlier_deadline_gets_earlier_slot(clean_db):
    now = datetime.now()
    early = create_task("Early task", "medium", now + timedelta(hours=3), 30)
    late = create_task("Late task", "high", now + timedelta(hours=8), 30)
    with get_conn() as conn:
        generate_schedule(conn)
    with get_conn() as conn:
        be = _blocks_for(conn, early["id"])
        bl = _blocks_for(conn, late["id"])
    assert datetime.fromisoformat(be[0]["start_time"]) <= datetime.fromisoformat(
        bl[0]["start_time"]
    ), "earlier deadline must be scheduled first regardless of priority"


def test_no_free_slot_reports_unscheduled(clean_db, monkeypatch):
    """A task longer than the horizon capacity is only partially scheduled and reported."""
    from app.config import settings

    monkeypatch.setattr(settings, "schedule_horizon_days", 1)
    now = datetime.now()
    t = create_task("Impossible task", "high", now + timedelta(days=1), 10 * 60)
    with get_conn() as conn:
        result = generate_schedule(conn)
    partial = [u for u in result["unscheduled"] if u["task_id"] == t["id"]]
    assert partial, "task that cannot fully fit must be reported as unscheduled (partial)"
    assert partial[0]["placed_minutes"] < 600
    assert any("do not fit" in e for e in result["explanations"])


def test_long_task_is_chunked_across_days(clean_db):
    now = datetime.now()
    t = create_task("Big project", "high", now + timedelta(days=3), 2 * 60)
    with get_conn() as conn:
        generate_schedule(conn)
    with get_conn() as conn:
        blocks = _blocks_for(conn, t["id"])
    total = sum(
        (datetime.fromisoformat(b["end_time"]) - datetime.fromisoformat(b["start_time"])).total_seconds()
        / 60
        for b in blocks
    )
    assert total == 120, "chunked blocks must cover the full duration"


def test_replan_moves_missed_task_and_explains(clean_db):
    now = datetime.now()
    t = create_task("Missed report", "medium", now - timedelta(hours=2), 30)
    with get_conn() as conn:
        generate_schedule(conn)
    with get_conn() as conn:
        result = replan(conn)
    assert result["missed_count"] == 1
    assert any("Missed report" in c for c in result["changes"])
    with get_conn() as conn:
        row = dict(conn.execute("SELECT * FROM tasks WHERE id = ?", (t["id"],)).fetchone())
        assert row["status"] == "todo"
        assert datetime.fromisoformat(row["deadline"]) > now
        new_blocks = _blocks_for(conn, t["id"])
    assert new_blocks, "replanned task must get a new schedule block"


def test_replan_with_no_missed_tasks_is_noop(clean_db):
    now = datetime.now()
    create_task("Future task", "high", now + timedelta(days=1), 30)
    with get_conn() as conn:
        result = replan(conn)
    assert result["missed_count"] == 0
    assert result["changes"] == []


def test_generate_schedule_replaces_future_blocks(clean_db):
    """Regenerating the schedule must not duplicate blocks for already-scheduled tasks."""
    t = create_task("Once only", "medium", datetime.now() + timedelta(days=1), 30)
    with get_conn() as conn:
        generate_schedule(conn)
    with get_conn() as conn:
        generate_schedule(conn)
    with get_conn() as conn:
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM schedule_blocks WHERE task_id = ?", (t["id"],)
        ).fetchone()["n"]
    assert n == 1, "regenerating must replace, not duplicate, future blocks"


def test_completed_task_releases_its_time(clean_db):
    """A done task's future block must not block new scheduling."""
    from app.services.tasks import complete_task

    t1 = create_task("Done early", "high", datetime.now() + timedelta(hours=5), 60)
    with get_conn() as conn:
        generate_schedule(conn)
    complete_task(t1["id"])
    t2 = create_task("New work", "high", datetime.now() + timedelta(hours=6), 60)
    with get_conn() as conn:
        generate_schedule(conn)
    with get_conn() as conn:
        b2 = _blocks_for(conn, t2["id"])
    assert b2, "new task should be scheduled"
    start = datetime.fromisoformat(b2[0]["start_time"])
    assert (start - datetime.now()).total_seconds() / 60 < 120, (
        "new task should reuse the time freed by the completed task"
    )


def test_blocks_do_not_overlap(clean_db):
    now = datetime.now()
    create_task("A", "high", now + timedelta(days=1), 60)
    create_task("B", "medium", now + timedelta(days=1), 60)
    create_task("C", "low", now + timedelta(days=1), 60)
    with get_conn() as conn:
        generate_schedule(conn)
    with get_conn() as conn:
        rows = [
            (datetime.fromisoformat(r["start_time"]), datetime.fromisoformat(r["end_time"]))
            for r in conn.execute("SELECT * FROM schedule_blocks ORDER BY start_time").fetchall()
        ]
    for (s1, e1), (s2, e2) in zip(rows, rows[1:]):
        assert e1 <= s2, f"overlap detected: {s1}-{e1} vs {s2}-{e2}"
