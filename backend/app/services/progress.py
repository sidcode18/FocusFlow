"""Progress statistics for the dashboard."""
from datetime import datetime, timedelta

from app.config import settings
from app.db import get_conn


def _week_bounds() -> tuple[datetime, datetime]:
    now = datetime.now()
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0)
    return monday, monday + timedelta(days=7)


def get_progress() -> dict:
    now = datetime.now().isoformat(timespec="seconds")
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    week_start, week_end = _week_bounds()
    horizon = (datetime.now() + timedelta(days=settings.schedule_horizon_days)).isoformat(
        timespec="seconds"
    )

    with get_conn() as conn:
        counts = {
            r["status"]: r["n"]
            for r in conn.execute("SELECT status, COUNT(*) AS n FROM tasks GROUP BY status")
        }
        done = counts.get("done", 0)
        todo = counts.get("todo", 0)
        missed = counts.get("missed", 0)
        total = done + todo + missed

        due_today = conn.execute(
            "SELECT COUNT(*) AS n FROM tasks WHERE deadline >= ? AND deadline < ? AND status != 'done'",
            (today.isoformat(timespec="seconds"), tomorrow.isoformat(timespec="seconds")),
        ).fetchone()["n"]
        done_today = conn.execute(
            "SELECT COUNT(*) AS n FROM tasks WHERE completed_at >= ? AND completed_at < ?",
            (today.isoformat(timespec="seconds"), tomorrow.isoformat(timespec="seconds")),
        ).fetchone()["n"]
        overdue = conn.execute(
            "SELECT COUNT(*) AS n FROM tasks WHERE status = 'todo' AND deadline IS NOT NULL AND deadline < ?",
            (now,),
        ).fetchone()["n"]

        minutes_week = conn.execute(
            """SELECT COALESCE(SUM((julianday(end_time) - julianday(start_time)) * 24 * 60), 0) AS m
               FROM schedule_blocks WHERE start_time >= ? AND start_time < ?""",
            (week_start.isoformat(timespec="seconds"), week_end.isoformat(timespec="seconds")),
        ).fetchone()["m"]
        minutes_done = conn.execute(
            """SELECT COALESCE(SUM((julianday(end_time) - julianday(start_time)) * 24 * 60), 0) AS m
               FROM schedule_blocks sb JOIN tasks t ON t.id = sb.task_id
               WHERE t.status = 'done' AND sb.start_time >= ?""",
            (week_start.isoformat(timespec="seconds"),),
        ).fetchone()["m"]
        upcoming = conn.execute(
            "SELECT COUNT(*) AS n FROM tasks WHERE status = 'todo' AND deadline >= ? AND deadline <= ?",
            (now, horizon),
        ).fetchone()["n"]

    return {
        "total_tasks": total,
        "done": done,
        "todo": todo,
        "missed": missed,
        "completion_rate": round(done / total * 100, 1) if total else 0.0,
        "due_today": due_today,
        "done_today": done_today,
        "overdue": overdue,
        "hours_scheduled_this_week": round(minutes_week / 60, 1),
        "hours_completed_this_week": round(minutes_done / 60, 1),
        "upcoming_with_deadline": upcoming,
    }
