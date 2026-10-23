"""Schedule generation, blocks listing, and progress endpoints."""
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException

from app.db import get_conn
from app.models import GenerateScheduleRequest, ReplanRequest
from app.services.scheduler import generate_schedule, replan
from app.services.progress import get_progress
from app.services.tasks import TaskNotFoundError

router = APIRouter(prefix="/api", tags=["schedule"])


@router.get("/schedule")
def get_schedule(days: int = 7):
    now = datetime.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=max(1, min(days, 31)))
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT sb.*, t.title AS task_title, t.priority AS task_priority,
                      t.status AS task_status
               FROM schedule_blocks sb JOIN tasks t ON t.id = sb.task_id
               WHERE sb.end_time > ? AND sb.start_time < ?
               ORDER BY sb.start_time""",
            (start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")),
        ).fetchall()
    blocks = []
    for r in rows:
        b = dict(r)
        b["start_time"] = datetime.fromisoformat(b["start_time"])
        b["end_time"] = datetime.fromisoformat(b["end_time"])
        blocks.append(b)
    return {"blocks": blocks}


@router.post("/schedule/generate")
def generate(payload: GenerateScheduleRequest | None = None):
    with get_conn() as conn:
        result = generate_schedule(conn, reason=(payload.reason if payload else None))
    return {"scheduled_count": len(result["blocks"]), **result}


@router.post("/schedule/replan")
def replan_missed(payload: ReplanRequest | None = None):
    with get_conn() as conn:
        try:
            result = replan(
                conn,
                task_ids=payload.task_ids if payload else None,
                new_deadline=payload.new_deadline if payload else None,
            )
        except TaskNotFoundError:
            raise HTTPException(status_code=404, detail="Task not found")
    return {"replanned": result["missed_count"] > 0, **result}


@router.get("/progress")
def progress():
    return get_progress()


@router.get("/health")
def health():
    return {"status": "ok", "app": "FocusFlow API"}
