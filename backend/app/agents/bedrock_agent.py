"""Amazon Bedrock agent: natural language -> tool calls -> verified execution -> reply."""
import json
import logging
from datetime import datetime

import boto3
from botocore.config import Config

from app.config import settings
from app.agents.tools import TOOL_SPECS, execute_tool, tool_result_json

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 8


def _client():
    return boto3.client(
        "bedrock-runtime",
        region_name=settings.aws_region,
        config=Config(retries={"max_attempts": 2}, read_timeout=90),
    )


def _system_prompt() -> str:
    now = datetime.now()
    return f"""You are FocusFlow, a focused productivity agent.

Current local time: {now.strftime('%A %Y-%m-%d %H:%M')}.

Rules:
- All task changes MUST go through tools. Never claim an action you did not perform.
- When the user mentions multiple things to do, create one task per item with sensible
  deadlines and durations, then call generate_schedule once at the end.
- For complete/delete/reschedule you need a task_id; call list_tasks first to resolve
  titles to ids when you don't have one.
- If the user says a task was missed or asks to replan/reschedule their day, call replan_missed
  and explain the changes it reports.
- Deadlines you pass to tools must be ISO 8601 local time (e.g. {now.strftime('%Y-%m-%d')}T17:00:00).
- Keep replies short and concrete. After tool calls, summarize exactly what changed,
  including the schedule changes reported by the tools.
- If a tool returns ok=false, tell the user honestly what failed."""


def run_bedrock_agent(message: str, history: list[dict] | None = None) -> dict:
    """Run the tool-use loop. Returns {'reply', 'actions', 'error'}."""
    client = _client()
    tool_config = {
        "tools": [
            {"toolSpec": {"name": t["name"], "description": t["description"],
                          "inputSchema": {"json": t["input_schema"]}}}
            for t in TOOL_SPECS
        ]
    }

    messages = list(history or [])
    messages.append({"role": "user", "content": [{"text": message}]})

    actions: list[dict] = []
    for _ in range(MAX_TOOL_ROUNDS):
        try:
            resp = client.converse(
                modelId=settings.bedrock_model_id,
                messages=messages,
                system=[{"text": _system_prompt()}],
                toolConfig=tool_config,
            )
        except Exception as e:  # noqa: BLE001 - surface API failures honestly
            logger.exception("Bedrock converse failed")
            return {"reply": "", "actions": actions, "error": f"Bedrock API error: {e}"}

        out = resp.get("output", {})
        message_out = out.get("message", {"role": "assistant", "content": []})
        messages.append(message_out)
        stop = resp.get("stopReason")

        tool_uses = [c["toolUse"] for c in message_out.get("content", []) if "toolUse" in c]
        if stop == "tool_use" and tool_uses:
            results_content = []
            for tu in tool_uses:
                result = execute_tool(tu["name"], tu.get("input") or {})
                actions.append({
                    "tool": tu["name"],
                    "ok": result.get("ok", False),
                    "summary": result.get("summary") or result.get("error", ""),
                    "detail": result,
                })
                results_content.append({
                    "toolResult": {
                        "toolUseId": tu["toolUseId"],
                        "content": [{"json": result}],
                    }
                })
            messages.append({"role": "user", "content": results_content})
            continue

        text_parts = [c["text"] for c in message_out.get("content", []) if "text" in c]
        return {"reply": "\n".join(text_parts).strip(), "actions": actions, "error": None}

    return {"reply": "I hit my tool-call limit before finishing. Please try a smaller request.",
            "actions": actions, "error": "max_tool_rounds"}


def bedrock_available() -> bool:
    return settings.bedrock_configured()
