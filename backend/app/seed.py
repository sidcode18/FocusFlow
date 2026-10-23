"""Seeds realistic demo data (relative to today) when the database is empty."""
from datetime import datetime, timedelta

from app.config import settings
from app.db import get_conn, init_db
from app.services.scheduler import generate_schedule
from app.services.tasks import complete_task, create_task


def _at(day_offset: int, hour: int, minute: int = 0) -> datetime:
    d = (datetime.now() + timedelta(days=day_offset)).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )
    return d


def is_empty() -> bool:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM tasks").fetchone()["n"] == 0


def seed() -> dict:
    created: list[dict] = []

    # Already-completed history (before today)
    t = create_task("Clear inbox to zero", "low", _at(-1, 17), 30, "Morning sweep")
    complete_task(t["id"])
    created.append(t)
    t = create_task("Send weekly status update", "medium", _at(0, 11), 20)
    complete_task(t["id"])
    created.append(t)

    # Overdue task — the replan demo candidate
    created.append(create_task(
        "File expense report", "medium", _at(0, max(settings.work_start, datetime.now().hour - 2), 0),
        20, "Overdue — perfect for the replan demo",
    ))

    # Today
    created.append(create_task("Finish investor deck slides", "high", _at(0, 17), 90))
    created.append(create_task("Review PR #142 (payments flow)", "medium", _at(0, 18, 30), 30))
    created.append(create_task("Buy groceries", "low", _at(0, 20), 20))

    # Tomorrow
    created.append(create_task("Write MVP spec for FocusFlow", "high", _at(1, 12), 60))
    created.append(create_task("Prep team sync agenda", "low", _at(1, 15), 30))

    # Later this week
    created.append(create_task("Prepare hackathon demo script", "high", _at(3, 16), 45))
    created.append(create_task("Book dentist appointment", "low", _at(4, 17), 10))

    # Next week
    created.append(create_task("Plan sprint 8 backlog", "medium", _at(7, 12), 60))

    with get_conn() as conn:
        result = generate_schedule(conn)

    return {"created": len(created), "scheduled": len(result["blocks"]),
            "explanations": result["explanations"]}


def ensure_seeded() -> dict:
    init_db()
    if not settings.seed_demo:
        return {"seeded": False, "reason": "disabled by config"}
    if not is_empty():
        return {"seeded": False, "reason": "database not empty"}
    return {"seeded": True, **seed()}
