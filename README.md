# FocusFlow

An AI productivity agent you talk to in plain language. It turns requests into tasks
with deadlines, builds a deterministic schedule around your workday, and replans
automatically when a deadline is missed.

- **Stack**: Next.js 15 + TypeScript + Tailwind CSS 4 · Python FastAPI · official Python MCP SDK · Amazon Bedrock (Claude) · SQLite
- **License**: MIT

> Replies come from Amazon Bedrock when AWS credentials are configured. Without them, a
> deterministic rule-based mock agent answers, and every reply is tagged **Mock** or
> **Bedrock** so output is never passed off as AI. Voice input uses the browser's speech
> APIs (Chrome/Edge) with a typing fallback elsewhere.

---

## Architecture

```
┌─────────────────────────┐   HTTP/JSON    ┌──────────────────────────┐
│  Next.js 15 frontend    │ ─────────────► │  FastAPI backend :8000   │
│  (dashboard, calendar,  │                │  /api/tasks  /api/schedule│
│   chat, voice)          │ ◄───────────── │  /api/progress  /api/chat │
└─────────────────────────┘                └────────────┬─────────────┘
                                                        │
                    ┌───────────────────────────────────┤
                    ▼                                   ▼
   ┌─────────────────────────────┐     ┌──────────────────────────────┐
   │  Agent layer                │     │  MCP server :8001            │
   │  • Bedrock converse         │     │  (official Python MCP SDK)   │
   │    tool-use loop            │     │  Streamable HTTP at /mcp     │
   │  • Mock agent (labeled)     │     │  spec: 2025-11-25 handshake, │
   │  Shared tool registry ──────┼────►│  2026-07-28 modern           │
   └──────────────┬──────────────┘     └──────────────┬───────────────┘
                  ▼                                   ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  Task services (create/complete/delete/reschedule/schedule/  │
   │  replan/progress) — every write verified after execution     │
   └───────────────────────────┬──────────────────────────────────┘
                               ▼
                       SQLite (WAL) · data/focusflow.db
```

**Request paths**

1. **UI**: dashboard buttons and the chat panel call the FastAPI REST API.
2. **Chat**: `POST /api/chat` → Bedrock agent (tool-use loop) *or* labeled mock agent →
   shared tool executors → verified writes → reply + per-tool action log.
3. **MCP**: independent uvicorn service exposing the same operations as MCP tools over
   **Streamable HTTP**. Tested with the official Python MCP client (`mcp.client.streamable_http`).

### AWS services used

| Service | Usage |
| --- | --- |
| **Amazon Bedrock** | Claude (default `anthropic.claude-sonnet-4-20250514-v1:0`, configurable) via the `converse` API with tool configuration — natural-language understanding, tool selection, and the final user-facing explanation. |
| **SQLite (local)** | Persistence. Chosen deliberately over DynamoDB/RDS for a zero-infra local app. |

No other AWS services are required. Nothing is deployed; everything runs locally.

### MCP tools (all execute real, verified operations)

| Tool | Description |
| --- | --- |
| `create_task` | Create a task (title, priority, deadline, duration). |
| `complete_task` | Mark a task done; re-reads the row to verify persistence. |
| `delete_task` | Delete a task and cascade its schedule blocks; verifies deletion. |
| `reschedule_task` | Move the work block and/or push the deadline; reopens missed tasks. |
| `generate_schedule` | Deterministically schedule all open tasks into free work-window slots. |
| `replan_missed` | Extend missed deadlines (default: next workday 18:00) and rebuild; explains every change. |
| `get_progress` | Completion rate, done today, overdue count, hours scheduled. |
| `list_tasks` | List/filter tasks to resolve titles → ids. |

Protocol: **MCP spec 2025-11-25** negotiated at handshake (SDK also supports the
2026-07-28 modern version). Transport: Streamable HTTP at `http://localhost:8001/mcp`.

### Deterministic scheduling rules

- Work window: `FOCUSFLOW_WORK_START`–`FOCUSFLOW_WORK_END` local time (default 9:00–18:00),
  from *now* onward, horizon `FOCUSFLOW_HORIZON_DAYS` (default 14 days).
- Open tasks sorted by: earliest deadline → priority (high > medium > low) → age.
- Each task gets contiguous block(s) in remaining free time; long tasks chunk across days.
- Tasks that can't finish before their deadline are still scheduled, with an explicit
  "does not finish before its deadline" explanation.
- Completed tasks release their reserved time; regenerating replaces future blocks
  (no duplicates).
- Replan: todo tasks past their deadline are reopened with a new deadline
  (given, or next workday 18:00), stale blocks cleared, and every change is explained
  in the API response and the UI.

---

## Quick start

Prerequisites: **Python 3.11+** and **Node.js 18+**. No Docker, no GPU, no other services.

```bash
# 1. Backend dependencies
cd backend
python3 -m venv ../.venv && source ../.venv/bin/activate
pip install -r requirements.txt

# 2. Configuration (optional — without AWS keys the app runs the labeled mock agent)
cp ../.env.example backend/.env    # then edit backend/.env

# 3. Frontend
cd ../frontend
npm install

# 4. Run all three services (three terminals)
cd backend && uvicorn app.main:app --port 8000          # T1: REST API
cd backend && uvicorn mcp_server.server:app --port 8001 # T2: MCP server
cd frontend && npm run dev                              # T3: web UI (localhost:3000)
```

Or run everything with `./run-dev.sh` from the repo root.

Open **http://localhost:3000**. Demo data seeds automatically on first run
(11 tasks: completed history, an overdue task to exercise replan, and upcoming work).

> Port 3000 busy? `npx next dev -p 3001` — port 3001 is already in the default CORS
> list. Opening the UI via a LAN IP (e.g. `http://10.10.34.154:3001`) also works;
> override with `FOCUSFLOW_CORS_ORIGIN_REGEX` if needed.

### Credentials

| Variable | Required for |
| --- | --- |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` (or `AWS_PROFILE`) | Real Bedrock mode |
| `FOCUSFLOW_BEDROCK_MODEL_ID` | Model selection — must be enabled in your account/region |
| `AWS_REGION` | Bedrock region (default `us-east-1`) |
| `FOCUSFLOW_FORCE_MOCK=1` | Force the labeled mock agent even with credentials |

IAM permission needed: `bedrock:InvokeModel` (and `bedrock:InvokeModelWithResponseStream`)
on the chosen model. If Bedrock fails at runtime, the chat endpoint returns an explicit
error — it never silently downgrades to mock.

### Run the tests

```bash
source .venv/bin/activate
cd backend && python -m pytest
```

**Latest run: 45 passed.** Coverage includes: scheduler rules (ordering, chunking,
overload, replan, overlap, done-releases-time), task service CRUD + verification,
persistence across connections, all REST endpoints (validation 422s, 404s, CORS),
mock-agent intents, and a full **MCP integration suite** that boots the real server as
a subprocess and drives it with the official Python client over Streamable HTTP
(protocol version, tool list, full create→complete→reschedule→replan→delete lifecycle
verified in-database, error paths).

---

## Demo walkthrough

1. Open http://localhost:3000 — stats strip, today's tasks, weekly calendar generated
   from deadlines.
2. In the Assistant panel, send:
   `Add prepare keynote slides by Friday 3pm and email sponsors tomorrow 9am and review analytics dashboard today 6pm`
   → three tasks appear, the calendar re-flows, and each tool call is logged under the
   reply (create × 3, generate_schedule).
3. Click **Mark complete** on "Finish investor deck slides" — stats update and its
   calendar time is released.
4. Click **Replan missed** (the overdue expense report), confirm, and read the
   explanation: deadline moved to the next workday, stale block cleared, new slot found.
5. Verify MCP independently:
   ```bash
   curl -s http://localhost:8001/health
   cd backend && python -m pytest tests/test_mcp_integration.py -q
   ```
   The integration test drives `create_task`/`complete_task` over **Streamable HTTP**
   with the official MCP client (spec 2025-11-25) and verifies the writes in SQLite;
   the new task appears in the UI.
6. Switch the Assistant to the **Voice** tab and say `How am I doing?` into the mic
   (Chrome/Edge) — the reply is spoken back with live stats. Every answer is tagged
   **Bedrock** or **Mock**.

---

## Project layout

```
backend/
  app/
    config.py            env-driven settings (no hardcoded secrets)
    db.py                SQLite (WAL), schema
    models.py            pydantic request/response schemas
    seed.py              realistic demo data (relative to today)
    services/            tasks · scheduler (deterministic) · progress
    routers/             tasks · schedule · chat · health
    agents/              tools registry (shared) · bedrock_agent · mock_agent
  mcp_server/server.py   MCP over Streamable HTTP (independent service)
  tests/                 45 tests incl. MCP client integration
frontend/
  src/app/               dashboard page, layout, global styles
  src/components/        Header · StatsStrip · TaskList · WeekCalendar ·
                         AssistantPanel (chat + voice) · modals
  src/lib/api.ts         typed API client
```

## Tested vs. not

**Tested (automated + manual):**
- All REST endpoints, validation and error paths (404/422), CORS.
- Deterministic scheduler: ordering, chunking, overload reporting, replanning,
  overlap-freedom, completed-task time release.
- Persistence: writes verified in SQLite across independent connections/processes.
- MCP: protocol handshake (2025-11-25), tool listing, full lifecycle, error handling —
  against the real server process over Streamable HTTP.
- Mock agent intents: multi-task creation, complete/delete/reschedule by title,
  replan, progress, unknown-task honesty.
- UI rendering verified in a browser (dashboard, lists, calendar, reply tags, voice
  controls, seeded state). One manual click-through is still recommended.

**Known limitations:**
- Single-user, no authentication; not hardened for public deployment.
- Mock agent NLU is rule-based — simple phrasings only; Bedrock mode handles
  free-form language.
- No timezone support (local naive time); no recurring tasks; no calendar export.
- Voice input depends on browser support (Chrome/Edge); spoken replies use
  `speechSynthesis`.
- Bedrock tool-use was exercised structurally (schemas, loop, verification); live
  Bedrock calls require credentials and were not run in the development environment.

## Notes from building with Bedrock and MCP

- Bedrock's `converse` tool-use API makes the agent loop straightforward — no custom
  prompt parsing — but per-region model availability is the main friction: the model id
  must match what the account has enabled, hence the env override and labeled mock
  fallback.
- The MCP spec's Streamable HTTP transport worked first-try with the official Python
  SDK; having the agent and MCP share one tool registry prevents drift between what
  the AI can do and what integrators can do.
- A "verified execution" pattern (re-read state after every write) caught real bugs
  during development and makes agent claims auditable — recommended for any agent
  built on this stack.
