"""Task CRUD and mutations. Single source of truth used by REST API, MCP tools and agents."""
import sqlite3
import uuid
from datetime import datetime
from typing import Any, Optional

from app.db import get_conn


class TaskNotFoundError(Exception):
    pass


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _row_to_task(row: sqlite3.Row) -> dict:  # type: ignore[name-defined]
    return dict(row)


def _get_task(conn, task_id: str) -> dict:
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise TaskNotFoundError(f"Task {task_id} not found")
    return _row_to_task(row)


def _bump(conn, task_id: str) -> None:
    conn.execute("UPDATE tasks SET updated_at = ? WHERE id = ?", (_now(), task_id))


def list_tasks(
    status: Optional[str] = None,
    include_done: bool = True,
    before: Optional[datetime] = None,
    after: Optional[datetime] = None,
) -> list[dict]:
    query = "SELECT * FROM tasks WHERE 1=1"
    params: list[Any] = []
    if status:
        query += " AND status = ?"
        params.append(status)
    elif not include_done:
        query += " AND status != 'done'"
    if before:
        query += " AND deadline IS NOT NULL AND deadline < ?"
        params.append(before.isoformat(timespec="seconds"))
    if after:
        query += " AND deadline IS NOT NULL AND deadline >= ?"
        params.append(after.isoformat(timespec="seconds"))
    query += " ORDER BY CASE deadline WHEN NULL THEN 1 ELSE 0 END, deadline ASC, created_at ASC"
    with get_conn() as conn:
        return [_row_to_task(r) for r in conn.execute(query, params).fetchall()]


def get_task(task_id: str) -> dict:
    with get_conn() as conn:
        return _get_task(conn, task_id)


def create_task(
    title: str,
    priority: str = "medium",
    deadline: Optional[datetime] = None,
    duration_minutes: int = 30,
    notes: Optional[str] = None,
) -> dict:
    now = _now()
    task_id = uuid.uuid4().hex[:12]
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO tasks (id, title, notes, priority, deadline, duration_minutes,
                                  status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 'todo', ?, ?)""",
            (
                task_id,
                title.strip(),
                notes,
                priority,
                deadline.isoformat(timespec="seconds") if deadline else None,
                int(duration_minutes),
                now,
                now,
            ),
        )
        return _get_task(conn, task_id)


def update_task(task_id: str, fields: dict) -> dict:
    allowed = {"title", "notes", "priority", "deadline", "duration_minutes", "status"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return get_task(task_id)
    if "deadline" in updates and isinstance(updates["deadline"], datetime):
        updates["deadline"] = updates["deadline"].isoformat(timespec="seconds")
    if "status" in updates and updates["status"] == "done" and "completed_at" not in updates:
        updates["completed_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    with get_conn() as conn:
        _get_task(conn, task_id)  # raises if missing
        conn.execute(f"UPDATE tasks SET {set_clause}, updated_at = ? WHERE id = ?",
                     (*updates.values(), _now(), task_id))
        return _get_task(conn, task_id)


def complete_task(task_id: str) -> dict:
    """Mark a task done. Verified: re-reads the row and asserts the new state."""
    with get_conn() as conn:
        task = _get_task(conn, task_id)
        conn.execute(
            "UPDATE tasks SET status = 'done', completed_at = ?, updated_at = ? WHERE id = ?",
            (_now(), _now(), task_id),
        )
        updated = _get_task(conn, task_id)
    assert updated["status"] == "done", "completion write did not persist"
    return updated


def reopen_task(task_id: str) -> dict:
    with get_conn() as conn:
        _get_task(conn, task_id)
        conn.execute(
            "UPDATE tasks SET status = 'todo', completed_at = NULL, updated_at = ? WHERE id = ?",
            (_now(), task_id),
        )
        return _get_task(conn, task_id)


def delete_task(task_id: str) -> dict:
    """Delete a task and its schedule blocks. Returns the deleted task for confirmation."""
    with get_conn() as conn:
        task = _get_task(conn, task_id)
        conn.execute("DELETE FROM schedule_blocks WHERE task_id = ?", (task_id,))
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        gone = conn.execute("SELECT id FROM tasks WHERE id = ?", (task_id,)).fetchone()
    assert gone is None, "delete did not persist"
    return task


def reschedule_task(
    task_id: str,
    new_start: Optional[datetime] = None,
    new_deadline: Optional[datetime] = None,
    reason: Optional[str] = None,
) -> dict:
    """Move a task's work block to new_start and/or push its deadline.

    - new_start: replaces the task's future schedule block(s) with one block at new_start.
    - new_deadline: updates the deadline; a missed task with a future deadline becomes todo again.
    """
    from app.services.scheduler import place_block, remove_future_blocks

    with get_conn() as conn:
        task = _get_task(conn, task_id)
        changes: list[str] = []

        if new_deadline is not None:
            old_deadline = task["deadline"]
            conn.execute(
                "UPDATE tasks SET deadline = ?, updated_at = ? WHERE id = ?",
                (new_deadline.isoformat(timespec="seconds"), _now(), task_id),
            )
            if task["status"] == "missed" and new_deadline > datetime.now():
                conn.execute(
                    "UPDATE tasks SET status = 'todo', updated_at = ? WHERE id = ?",
                    (_now(), task_id),
                )
                changes.append(f"reopened missed task (deadline was {old_deadline})")
            changes.append(f"deadline -> {new_deadline.strftime('%a %b %d %H:%M')}")

        task = _get_task(conn, task_id)

        if new_start is not None:
            removed = remove_future_blocks(conn, task_id)
            end = place_block(conn, task, new_start, kind="replan", reason=reason)
            changes.append(
                f"moved work block to {new_start.strftime('%a %b %d %H:%M')}"
                + (f" (cleared {removed} old block(s))" if removed else "")
            )
            result_block_end = end.isoformat(timespec="seconds")
        else:
            result_block_end = None

        final = _get_task(conn, task_id)
        blocks = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM schedule_blocks WHERE task_id = ? ORDER BY start_time", (task_id,)
            ).fetchall()
        ]
    return {"task": final, "blocks": blocks, "changes": changes, "block_end": result_block_end}
