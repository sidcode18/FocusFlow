"""MCP integration tests over Streamable HTTP.

Boots the real MCP server as an independent uvicorn subprocess (like production),
then drives it with the official Python MCP client:
  mcp.client.streamable_http.streamable_http_client

Asserts protocol version >= 2025-11-25, tool discovery, and that tool calls
perform real, verifiable database operations.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import anyio
import mcp_types.version as v
import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
MIN_PROTOCOL = "2025-11-25"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def mcp_server():
    tmp = Path(tempfile.mkdtemp(prefix="focusflow_mcp_test_"))
    db_path = tmp / "mcp_test.db"
    port = _free_port()
    env = dict(os.environ)
    env["FOCUSFLOW_DB_PATH"] = str(db_path)
    env["FOCUSFLOW_SEED_DEMO"] = "0"
    env["PYTHONPATH"] = str(BACKEND_DIR)
    proc = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "mcp_server.server:app", "--port", str(port),
         "--log-level", "warning"],
        cwd=BACKEND_DIR, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    last_err = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base}/health", timeout=1) as r:
                if r.status == 200:
                    break
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(0.3)
    else:
        proc.terminate()
        err = proc.stderr.read().decode()[-2000:] if proc.stderr else ""
        raise RuntimeError(f"MCP test server did not start: {last_err}\n{err}")

    yield {"base": base, "db_path": str(db_path), "proc": proc}
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="module")
def db_path(mcp_server):
    return mcp_server["db_path"]


def _run(coro_fn):
    return anyio.run(coro_fn)


def test_mcp_health(mcp_server):
    with urllib.request.urlopen(f"{mcp_server['base']}/health", timeout=5) as r:
        body = json.loads(r.read())
    assert body["status"] == "ok"
    assert body["transport"] == "streamable-http"
    assert body["database_ok"] is True


def test_protocol_version_and_tools(mcp_server):
    async def go():
        from mcp.client.session import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(f"{mcp_server['base']}/mcp") as streams:
            read_stream, write_stream = streams
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                return session.protocol_version, \
                    sorted(t.name for t in (await session.list_tools()).tools)

    protocol, tools = _run(go)
    assert v.HANDSHAKE_PROTOCOL_VERSIONS.index(protocol) >= v.HANDSHAKE_PROTOCOL_VERSIONS.index(
        MIN_PROTOCOL
    ), f"negotiated {protocol} < required {MIN_PROTOCOL}"
    for required in [
        "create_task", "complete_task", "delete_task", "reschedule_task",
        "generate_schedule", "replan_missed", "get_progress", "list_tasks",
    ]:
        assert required in tools, f"missing MCP tool {required}"


def test_full_tool_lifecycle_with_verification(mcp_server, db_path):
    """create -> verify in DB; complete -> verify; reschedule -> verify; delete -> verify."""
    deadline = (datetime.now() + timedelta(days=2)).replace(microsecond=0)

    async def go():
        from mcp.client.session import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(f"{mcp_server['base']}/mcp") as streams:
            read_stream, write_stream = streams
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                async def call(name, args):
                    res = await session.call_tool(name, args)
                    return json.loads(res.content[0].text)

                created = await call("create_task", {
                    "title": "MCP lifecycle task", "priority": "high",
                    "deadline": deadline.isoformat(timespec="seconds"),
                    "duration_minutes": 50,
                })
                assert created["ok"], created
                task_id = created["task"]["id"]

                listed = await call("list_tasks", {"status": "todo"})
                assert any(t["id"] == task_id for t in listed["tasks"])

                sched = await call("generate_schedule", {})
                assert sched["ok"] and sched["scheduled_count"] >= 1

                done = await call("complete_task", {"task_id": task_id})
                assert done["ok"] and done["task"]["status"] == "done"

                reopened = await call("reschedule_task", {
                    "task_id": task_id,
                    "new_deadline": (deadline + timedelta(days=1)).isoformat(timespec="seconds"),
                })
                assert reopened["ok"], reopened

                progress = await call("get_progress", {})
                assert progress["ok"] and progress["progress"]["total_tasks"] >= 1

                deleted = await call("delete_task", {"task_id": task_id})
                assert deleted["ok"]

                after = await call("list_tasks", {})
                assert all(t["id"] != task_id for t in after["tasks"])
                return True

    assert _run(go)
    # Cross-process verification: the same SQLite file holds what MCP wrote
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM tasks WHERE title = ?", ("MCP lifecycle task",)
    ).fetchall()
    conn.close()
    assert len(rows) == 0, "deleted task must be gone from disk"


def test_replan_tool_over_mcp(mcp_server):
    past = (datetime.now() - timedelta(hours=3)).replace(microsecond=0)

    async def go():
        from mcp.client.session import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(f"{mcp_server['base']}/mcp") as streams:
            read_stream, write_stream = streams
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                async def call(name, args):
                    res = await session.call_tool(name, args)
                    return json.loads(res.content[0].text)

                created = await call("create_task", {
                    "title": "MCP missed task", "deadline": past.isoformat(timespec="seconds"),
                })
                assert created["ok"]
                replanned = await call("replan_missed", {})
                assert replanned["ok"], replanned
                assert replanned["missed_count"] >= 1
                assert replanned["changes"], "replan must explain its changes"
                return replanned

    result = _run(go)
    assert any("MCP missed task" in c for c in result["changes"])


def test_unknown_tool_reports_error(mcp_server):
    async def go():
        from mcp.client.session import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(f"{mcp_server['base']}/mcp") as streams:
            read_stream, write_stream = streams
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                return await session.call_tool("no_such_tool", {})

    res = _run(go)
    # MCP-standard error path: the result must be flagged as an error, not silently succeed
    assert res.is_error, res
    text = " ".join(getattr(c, "text", "") for c in res.content)
    assert "unknown" in text.lower() or "no_such_tool" in text.lower()


def test_invalid_input_reports_error(mcp_server):
    async def go():
        from mcp.client.session import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(f"{mcp_server['base']}/mcp") as streams:
            read_stream, write_stream = streams
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                res = await session.call_tool("complete_task", {"task_id": "ghost"})
                return json.loads(res.content[0].text)

    result = _run(go)
    assert result["ok"] is False
    assert "not found" in result["error"].lower()
