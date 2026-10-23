"""FocusFlow MCP server — Model Context Protocol over Streamable HTTP.

Built with the official Python MCP SDK (mcp>=2.3.0). Protocol support:
- Handshake protocol versions through 2025-11-25 (LATEST_HANDSHAKE_VERSION)
- Modern protocol version 2026-07-28 (LATEST_MODERN_VERSION)

Run independently:
    cd backend && uvicorn mcp_server.server:app --port 8001

Endpoint:  http://127.0.0.1:8001/mcp   (Streamable HTTP)
Health:    http://127.0.0.1:8001/health
"""
import logging

from starlette.requests import Request
from starlette.responses import JSONResponse

from app.db import init_db
from app.seed import ensure_seeded
from app.services import tasks as task_service
from app.agents.tools import EXECUTORS, execute_tool

from mcp.server.mcpserver import MCPServer

logger = logging.getLogger(__name__)

server = MCPServer(
    name="FocusFlow Task Tools",
    title="FocusFlow Task Tools",
    description=(
        "Real task operations for FocusFlow: create, complete, delete, reschedule tasks, "
        "generate deterministic schedules, replan missed work, and read progress. "
        "All tools execute against the FocusFlow SQLite store and verify their results."
    ),
    version="1.0.0",
)


@server.tool()
def create_task(
    title: str,
    priority: str = "medium",
    deadline: str | None = None,
    duration_minutes: int = 30,
    notes: str | None = None,
) -> dict:
    """Create a task. deadline is ISO 8601 local time (e.g. 2026-10-23T17:00:00), optional."""
    return execute_tool("create_task", {
        "title": title, "priority": priority, "deadline": deadline,
        "duration_minutes": duration_minutes, "notes": notes,
    })


@server.tool()
def complete_task(task_id: str) -> dict:
    """Mark a task as done by id."""
    return execute_tool("complete_task", {"task_id": task_id})


@server.tool()
def delete_task(task_id: str) -> dict:
    """Permanently delete a task and its schedule blocks by id."""
    return execute_tool("delete_task", {"task_id": task_id})


@server.tool()
def reschedule_task(
    task_id: str,
    new_start: str | None = None,
    new_deadline: str | None = None,
    reason: str | None = None,
) -> dict:
    """Move a task's work block (new_start) and/or push its deadline (new_deadline), ISO 8601."""
    return execute_tool("reschedule_task", {
        "task_id": task_id, "new_start": new_start,
        "new_deadline": new_deadline, "reason": reason,
    })


@server.tool()
def generate_schedule() -> dict:
    """Deterministically schedule all open tasks into free work-window slots."""
    return execute_tool("generate_schedule", {})


@server.tool()
def replan_missed(task_ids: list[str] | None = None, new_deadline: str | None = None) -> dict:
    """Recover tasks that missed their deadlines: extend deadlines and rebuild the schedule."""
    return execute_tool("replan_missed", {"task_ids": task_ids, "new_deadline": new_deadline})


@server.tool()
def get_progress() -> dict:
    """Productivity statistics: completion rate, done today, overdue, hours scheduled."""
    return execute_tool("get_progress", {})


@server.tool()
def list_tasks(status: str | None = None) -> dict:
    """List tasks, optionally filtered by status: todo | done | missed."""
    return execute_tool("list_tasks", {"status": status})


async def health(request: Request) -> JSONResponse:
    try:
        task_service.list_tasks()
        db_ok = True
        error = None
    except Exception as e:  # noqa: BLE001
        db_ok, error = False, str(e)
    return JSONResponse(
        {"status": "ok" if db_ok else "degraded", "service": "FocusFlow MCP",
         "transport": "streamable-http", "endpoint": "/mcp",
         "mcp_sdk": ">=2.3.0 (protocol 2025-11-25 handshake, 2026-07-28 modern)",
         "database_ok": db_ok, "database_error": error}
    )


_raw_app = server.streamable_http_app()
_original_lifespan = _raw_app.router.lifespan_context


from contextlib import asynccontextmanager  # noqa: E402


@asynccontextmanager
async def _lifespan(app):  # noqa: ANN201
    init_db()
    result = ensure_seeded()
    if result.get("seeded"):
        logger.info("MCP server seeded demo data: %s tasks", result["created"])
    async with _original_lifespan(app):
        yield


_raw_app.router.lifespan_context = _lifespan
app = _raw_app
app.router.add_route("/health", health, methods=["GET"])
