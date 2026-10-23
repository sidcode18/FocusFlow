"""Shared agent tool registry.

One definition of each tool (JSON schema + executor) is reused by:
- the Bedrock agent (tool-use loop), and
- the MCP server (which wraps the same executors as MCP tools).

Every executor performs a real backend operation and verifies the result
before returning, so agent claims are backed by checked database state.
"""
import json
from datetime import datetime
from typing import Any, Callable, Optional

from app.db import get_conn
from app.services import tasks as task_service
from app.services.progress import get_progress
from app.services.scheduler import generate_schedule, replan
from app.services.tasks import TaskNotFoundError

TOOL_SPECS: list[dict] = [
    {
        "name": "create_task",
        "description": (
            "Create a new task with a title, priority, optional deadline and duration in minutes. "
            "Use for anything the user asks to add, remind about, or plan."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short task title"},
                "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                "deadline": {
                    "type": "string",
                    "description": "Deadline in ISO 8601 local time, e.g. 2026-10-23T17:00:00. Omit if unknown.",
                },
                "duration_minutes": {"type": "integer", "minimum": 5, "maximum": 600},
                "notes": {"type": "string"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "complete_task",
        "description": "Mark an existing task as done. Requires the task id (look it up with list_tasks first if needed).",
        "input_schema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "delete_task",
        "description": "Permanently delete a task and its scheduled blocks. Only call when the user clearly asks to delete/remove it.",
        "input_schema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "reschedule_task",
        "description": (
            "Reschedule a task: move its work block to a new start time and/or push its deadline. "
            "A missed task with a new future deadline is reopened."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "new_start": {"type": "string", "description": "ISO 8601 local time for the work block"},
                "new_deadline": {"type": "string", "description": "ISO 8601 local time"},
                "reason": {"type": "string"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "generate_schedule",
        "description": "Deterministically schedule all open tasks into free work-window slots based on deadlines and durations.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "replan_missed",
        "description": (
            "Find tasks that missed their deadlines, extend them (default: next workday end) and rebuild the schedule. "
            "Explains every change."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_ids": {"type": "array", "items": {"type": "string"}},
                "new_deadline": {"type": "string"},
            },
        },
    },
    {
        "name": "get_progress",
        "description": "Get productivity statistics: completion rate, done today, overdue count, hours scheduled this week.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_tasks",
        "description": "List tasks, optionally filtered by status (todo/done/missed). Use to find task ids by title.",
        "input_schema": {
            "type": "object",
            "properties": {"status": {"type": "string", "enum": ["todo", "done", "missed"]}},
        },
    },
]


def _iso(value: Any) -> Any:
    if isinstance(value, str):
        return value
    return value.isoformat(timespec="seconds")


# --- Executors: real operations + verification ---------------------------------


def exec_create_task(args: dict) -> dict:
    deadline = _parse_dt(args.get("deadline"))
    task = task_service.create_task(
        title=args["title"],
        priority=args.get("priority", "medium"),
        deadline=deadline,
        duration_minutes=args.get("duration_minutes", 30),
        notes=args.get("notes"),
    )
    stored = task_service.get_task(task["id"])
    assert stored["title"] == task["title"] and stored["status"] == "todo"
    return {"ok": True, "task": stored,
            "summary": f"Created '{stored['title']}' ({stored['priority']}, "
                       f"{stored['duration_minutes']} min)"}


def exec_complete_task(args: dict) -> dict:
    task = task_service.complete_task(args["task_id"])
    return {"ok": True, "task": task, "summary": f"Completed '{task['title']}'"}


def exec_delete_task(args: dict) -> dict:
    deleted = task_service.delete_task(args["task_id"])
    return {"ok": True, "task": deleted, "summary": f"Deleted '{deleted['title']}'"}


def exec_reschedule_task(args: dict) -> dict:
    result = task_service.reschedule_task(
        args["task_id"],
        new_start=_parse_dt(args.get("new_start")),
        new_deadline=_parse_dt(args.get("new_deadline")),
        reason=args.get("reason"),
    )
    t = result["task"]
    return {"ok": True, "task": t, "changes": result["changes"],
            "summary": f"Rescheduled '{t['title']}': " + ("; ".join(result["changes"]) or "no changes")}


def exec_generate_schedule(args: dict) -> dict:
    with get_conn() as conn:
        result = generate_schedule(conn)
    return {"ok": True, "scheduled_count": len(result["blocks"]),
            "explanations": result["explanations"], "unscheduled": result["unscheduled"],
            "summary": f"Scheduled {len(result['blocks'])} block(s). "
                       + " ".join(result["explanations"][:5])}


def exec_replan_missed(args: dict) -> dict:
    with get_conn() as conn:
        result = replan(conn, task_ids=args.get("task_ids"),
                        new_deadline=_parse_dt(args.get("new_deadline")))
    return {"ok": True, **result,
            "summary": (f"Replanned {result['missed_count']} missed task(s). "
                        + " ".join(result["changes"] + result["explanations"][:5]))[:1000]}


def exec_get_progress(args: dict) -> dict:
    p = get_progress()
    return {"ok": True, "progress": p, "detail": {"progress": p},
            "summary": (f"{p['done']}/{p['total_tasks']} tasks done "
                        f"({p['completion_rate']}%), {p['overdue']} overdue, "
                        f"{p['done_today']} done today.")}


def exec_list_tasks(args: dict) -> dict:
    items = task_service.list_tasks(status=args.get("status"))
    return {"ok": True, "tasks": items,
            "summary": f"{len(items)} task(s): "
                       + "; ".join(f"{t['title']} [{t['status']}]" for t in items[:10])}


EXECUTORS: dict[str, Callable[[dict], dict]] = {
    "create_task": exec_create_task,
    "complete_task": exec_complete_task,
    "delete_task": exec_delete_task,
    "reschedule_task": exec_reschedule_task,
    "generate_schedule": exec_generate_schedule,
    "replan_missed": exec_replan_missed,
    "get_progress": exec_get_progress,
    "list_tasks": exec_list_tasks,
}


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def execute_tool(name: str, args: dict) -> dict:
    """Run a tool by name with error containment. Returns a JSON-safe dict."""
    fn = EXECUTORS.get(name)
    if fn is None:
        return {"ok": False, "tool": name, "error": f"Unknown tool: {name}"}
    try:
        result = fn(args or {})
        result["tool"] = name
        return result
    except TaskNotFoundError as e:
        return {"ok": False, "tool": name, "error": str(e)}
    except (KeyError, ValueError, AssertionError) as e:
        return {"ok": False, "tool": name, "error": f"{type(e).__name__}: {e}"}


def tool_result_json(result: dict) -> str:
    return json.dumps(_safe(result), default=str)


def _safe(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat(timespec="seconds")
    if isinstance(obj, dict):
        return {k: _safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_safe(v) for v in obj]
    return obj
