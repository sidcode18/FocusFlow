"""Task CRUD endpoints."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.models import RescheduleRequest, TaskCreate, TaskOut, TaskUpdate
from app.services import tasks as task_service
from app.services.scheduler import replan
from app.db import get_conn

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _serialize(task: dict) -> dict:
    out = dict(task)
    for key in ("deadline", "completed_at", "created_at", "updated_at"):
        if out.get(key):
            out[key] = datetime.fromisoformat(out[key])
    return out


@router.get("")
def list_tasks(
    status: Optional[str] = Query(default=None, pattern="^(todo|done|missed)$"),
    include_done: bool = True,
):
    return [_serialize(t) for t in task_service.list_tasks(status=status, include_done=include_done)]


@router.get("/{task_id}")
def get_task(task_id: str):
    try:
        return _serialize(task_service.get_task(task_id))
    except task_service.TaskNotFoundError:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")


@router.post("", status_code=201)
def create_task(payload: TaskCreate):
    task = task_service.create_task(
        title=payload.title,
        priority=payload.priority,
        deadline=payload.deadline,
        duration_minutes=payload.duration_minutes,
        notes=payload.notes,
    )
    return _serialize(task)


@router.patch("/{task_id}")
def update_task(task_id: str, payload: TaskUpdate):
    try:
        task = task_service.update_task(task_id, payload.model_dump(exclude_none=True))
    except task_service.TaskNotFoundError:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return _serialize(task)


@router.post("/{task_id}/complete")
def complete_task(task_id: str):
    try:
        return _serialize(task_service.complete_task(task_id))
    except task_service.TaskNotFoundError:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")


@router.post("/{task_id}/reopen")
def reopen_task(task_id: str):
    try:
        return _serialize(task_service.reopen_task(task_id))
    except task_service.TaskNotFoundError:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")


@router.delete("/{task_id}")
def delete_task(task_id: str):
    try:
        deleted = task_service.delete_task(task_id)
    except task_service.TaskNotFoundError:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return {"deleted": True, "task": _serialize(deleted)}


@router.post("/{task_id}/reschedule")
def reschedule_task(task_id: str, payload: RescheduleRequest):
    if payload.new_start is None and payload.new_deadline is None:
        raise HTTPException(status_code=422, detail="Provide new_start and/or new_deadline")
    try:
        result = task_service.reschedule_task(
            task_id,
            new_start=payload.new_start,
            new_deadline=payload.new_deadline,
            reason=payload.reason,
        )
    except task_service.TaskNotFoundError:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    result["task"] = _serialize(result["task"])
    return result


@router.post("/replan")
def replan_missed(payload: dict | None = None):
    body = payload or {}
    with get_conn() as conn:
        result = replan(
            conn,
            task_ids=body.get("task_ids"),
            new_deadline=(
                datetime.fromisoformat(body["new_deadline"]) if body.get("new_deadline") else None
            ),
        )
    return result
