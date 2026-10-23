"""Deterministic scheduler.

Rules (documented in README):
- Work window is FOCUSFLOW_WORK_START..FOCUSFLOW_WORK_END local time, from now onward.
- Todo tasks are scheduled earliest-deadline-first, then priority (high>medium>low), then age.
- Each task gets contiguous block(s) inside the work window; long tasks are chunked per day.
- If nothing fits before the deadline, the task is placed in the next free slot and flagged.
- Replan reuses the same rules after extending missed tasks' deadlines.
"""
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from app.config import settings
from app.db import get_conn

PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}


def _now() -> datetime:
    return datetime.now().replace(second=0, microsecond=0)


def _work_windows(horizon_days: int | None = None) -> list[tuple[datetime, datetime]]:
    """Daily [work_start, work_end] windows for the next horizon days, starting today."""
    horizon = horizon_days or settings.schedule_horizon_days
    windows = []
    now = _now()
    for offset in range(horizon):
        day = (now + timedelta(days=offset)).replace(hour=settings.work_start, minute=0)
        end = (now + timedelta(days=offset)).replace(hour=settings.work_end, minute=0)
        if offset == 0:
            start = max(day, now + timedelta(minutes=5))
        else:
            start = day
        if start < end:
            windows.append((start, end))
    return windows


def _existing_blocks(conn) -> list[tuple[datetime, datetime]]:
    """Busy intervals from schedule blocks. Completed tasks release their time."""
    rows = conn.execute(
        """SELECT sb.start_time, sb.end_time
           FROM schedule_blocks sb JOIN tasks t ON t.id = sb.task_id
           WHERE t.status != 'done' AND sb.start_time >= ?
           ORDER BY sb.start_time""",
        (_now().isoformat(timespec="seconds"),),
    ).fetchall()
    return [
        (datetime.fromisoformat(r["start_time"]), datetime.fromisoformat(r["end_time"]))
        for r in rows
    ]


def _subtract(busy: list[tuple[datetime, datetime]],
              windows: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    """Free intervals = work windows minus busy blocks, merged and sorted."""
    events = []
    for s, e in windows:
        events.append((s, 1))
        events.append((e, -1))
    for s, e in busy:
        events.append((s, -1))
        events.append((e, 1))
    # Sweep line
    events.sort(key=lambda x: (x[0], x[1]))
    free: list[tuple[datetime, datetime]] = []
    depth = 0
    open_start: Optional[datetime] = None
    for t, delta in events:
        prev = depth
        depth += delta
        if prev == 0 and depth > 0:
            open_start = t
        elif prev > 0 and depth == 0 and open_start is not None:
            if t > open_start:
                free.append((open_start, t))
            open_start = None
    return free


def find_free_slots(conn) -> list[tuple[datetime, datetime]]:
    return _subtract(_existing_blocks(conn), _work_windows())


def place_block(conn, task: dict, start: datetime, kind: str = "work",
                reason: Optional[str] = None) -> datetime:
    """Insert a block for the task starting at start, duration = remaining duration."""
    end = start + timedelta(minutes=int(task["duration_minutes"]))
    conn.execute(
        """INSERT INTO schedule_blocks (id, task_id, start_time, end_time, kind, reason, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            uuid.uuid4().hex[:12],
            task["id"],
            start.isoformat(timespec="seconds"),
            end.isoformat(timespec="seconds"),
            kind,
            reason,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    return end


def remove_future_blocks(conn, task_id: str) -> int:
    cur = conn.execute(
        "DELETE FROM schedule_blocks WHERE task_id = ? AND start_time >= ?",
        (task_id, _now().isoformat(timespec="seconds")),
    )
    return cur.rowcount


def _sort_key(task: dict):
    deadline = task["deadline"]
    return (
        0 if deadline else 1,
        deadline or "9999",
        PRIORITY_RANK.get(task["priority"], 1),
        task["created_at"],
    )


def generate_schedule(conn, task_ids: Optional[list[str]] = None,
                      reason: Optional[str] = None) -> dict:
    """Schedule all (or selected) open tasks into free slots. Returns blocks + explanations."""
    if task_ids:
        placeholders = ",".join("?" for _ in task_ids)
        rows = conn.execute(
            f"SELECT * FROM tasks WHERE status = 'todo' AND id IN ({placeholders})", task_ids
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM tasks WHERE status = 'todo'").fetchall()
    tasks = sorted((dict(r) for r in rows), key=_sort_key)

    # Regeneration semantics: replace future blocks for the tasks being scheduled
    # (past blocks are kept as history).
    for task in tasks:
        remove_future_blocks(conn, task["id"])

    free = find_free_slots(conn)
    explanations: list[str] = []
    blocks: list[dict] = []
    unscheduled: list[dict] = []
    now = _now()

    for task in tasks:
        remaining = int(task["duration_minutes"])
        deadline = datetime.fromisoformat(task["deadline"]) if task["deadline"] else None
        placed_any = False
        overdue = False
        first_start: Optional[datetime] = None

        while remaining > 0:
            slot = next(((s, e) for s, e in free if (e - s).total_seconds() / 60 >= 5), None)
            if slot is None:
                break
            s, e = slot
            take = min(remaining, int((e - s).total_seconds() / 60))
            block_end = s + timedelta(minutes=take)
            if remaining - take > 0:
                block_end = e  # chunk fills the whole slot when continuing later
            conn.execute(
                """INSERT INTO schedule_blocks (id, task_id, start_time, end_time, kind, reason, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    uuid.uuid4().hex[:12],
                    task["id"],
                    s.isoformat(timespec="seconds"),
                    block_end.isoformat(timespec="seconds"),
                    "replan" if reason else "work",
                    reason,
                    now.isoformat(timespec="seconds"),
                ),
            )
            blocks.append({
                "task_id": task["id"], "start_time": s.isoformat(timespec="seconds"),
                "end_time": block_end.isoformat(timespec="seconds"),
            })
            if deadline and block_end > deadline:
                overdue = True
            if first_start is None:
                first_start = s
            # consume the used part of the slot
            free = [(block_end, b) if (a, b) == (s, e) else (a, b) for a, b in free]
            free = [(a, b) for a, b in free if b > a]
            remaining -= take
            placed_any = True

        if not placed_any:
            unscheduled.append({"task_id": task["id"], "title": task["title"],
                                "duration_minutes": task["duration_minutes"]})
            explanations.append(
                f"Could not schedule '{task['title']}' ({task['duration_minutes']} min) — "
                f"no free slot in the work window for the next {settings.schedule_horizon_days} days."
            )
            continue
        when = first_start.strftime("%a %b %d %H:%M") if first_start else "?"
        if remaining > 0:
            placed = task["duration_minutes"] - remaining
            unscheduled.append({"task_id": task["id"], "title": task["title"],
                                "duration_minutes": remaining,
                                "placed_minutes": placed})
            explanations.append(
                f"Scheduled {placed} of {task['duration_minutes']} min for '{task['title']}' "
                f"starting {when}; the remaining {remaining} min do not fit before the "
                f"{settings.schedule_horizon_days}-day horizon — free up time or extend the deadline."
            )
        elif overdue:
            explanations.append(
                f"Scheduled '{task['title']}' at {when}, but it does not finish before its "
                f"deadline ({task['deadline']}) — consider extending the deadline."
            )
        else:
            explanations.append(f"Scheduled '{task['title']}' at {when}.")

    return {"blocks": blocks, "explanations": explanations, "unscheduled": unscheduled}


def replan(conn, task_ids: Optional[list[str]] = None,
           new_deadline: Optional[datetime] = None) -> dict:
    """Mark overdue todo tasks as missed, extend their deadlines, and reschedule them."""
    now = _now()
    if task_ids:
        placeholders = ",".join("?" for _ in task_ids)
        rows = conn.execute(
            f"SELECT * FROM tasks WHERE id IN ({placeholders}) AND status != 'done'", task_ids
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE status = 'todo' AND deadline IS NOT NULL AND deadline < ?",
            (now.isoformat(timespec="seconds"),),
        ).fetchall()

    missed = [dict(r) for r in rows]
    changes: list[str] = []

    if new_deadline is None:
        tomorrow = (now + timedelta(days=1)).date()
        new_deadline = datetime.combine(tomorrow, datetime.min.time()).replace(
            hour=settings.work_end
        )
        default_deadline = True
    else:
        default_deadline = False

    ids: list[str] = []
    for task in missed:
        old = task["deadline"]
        conn.execute(
            "UPDATE tasks SET deadline = ?, status = 'todo', updated_at = ? WHERE id = ?",
            (new_deadline.isoformat(timespec="seconds"), now.isoformat(timespec="seconds"),
             task["id"]),
        )
        removed = remove_future_blocks(conn, task["id"])
        ids.append(task["id"])
        changes.append(
            f"'{task['title']}' missed its deadline ({old}); deadline moved to "
            f"{new_deadline.strftime('%a %b %d %H:%M')}"
            + (" (default: next workday end)" if default_deadline else "")
            + f"; cleared {removed} stale block(s)."
        )

    result = generate_schedule(conn, task_ids=ids or None,
                               reason="replan after missed deadline")
    return {"missed_count": len(missed), "changes": changes,
            "explanations": result["explanations"], "blocks": result["blocks"]}
