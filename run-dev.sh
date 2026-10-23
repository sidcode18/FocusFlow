#!/usr/bin/env bash
# FocusFlow dev launcher: starts API (:8000), MCP (:8001), frontend (:3000 or 3001).
# Usage: ./run-dev.sh          (Ctrl+C stops everything)
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "Creating Python venv + installing backend deps..."
  python3 -m venv .venv
  ./.venv/bin/pip install -q -r backend/requirements.txt
fi

if [ ! -d frontend/node_modules ]; then
  echo "Installing frontend deps..."
  (cd frontend && npm install --no-audit --no-fund)
fi

cleanup() {
  [ -n "${API_PID:-}" ] && kill "$API_PID" 2>/dev/null || true
  [ -n "${MCP_PID:-}" ] && kill "$MCP_PID" 2>/dev/null || true
  [ -n "${WEB_PID:-}" ] && kill "$WEB_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

(cd backend && ../.venv/bin/uvicorn app.main:app --port 8000) & API_PID=$!
(cd backend && ../.venv/bin/uvicorn mcp_server.server:app --port 8001) & MCP_PID=$!

# Prefer 3000; fall back to 3001 if taken
WEB_PORT=3000
if (exec 3<>/dev/tcp/127.0.0.1/3000) 2>/dev/null; then
  WEB_PORT=3001
fi
(cd frontend && npx next dev -p "$WEB_PORT") & WEB_PID=$!

echo ""
echo "FocusFlow running:"
echo "  Web UI : http://localhost:$WEB_PORT"
echo "  API    : http://localhost:8000/api/health"
echo "  MCP    : http://localhost:8001/mcp  (health: http://localhost:8001/health)"
echo ""
wait
