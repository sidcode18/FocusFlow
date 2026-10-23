"""Chat endpoint: routes to the Bedrock agent or the deterministic mock agent.

The response's `mode` field always states which brain produced the reply:
- 'bedrock'  -> real Amazon Bedrock tool-use orchestration
- 'mock'     -> rule-based fallback, clearly labeled in the UI, never presented as AI
"""
import logging

from fastapi import APIRouter

from app.agents import bedrock_agent, mock_agent
from app.agents.tools import _safe
from app.config import settings
from app.models import AgentAction, ChatRequest, ChatResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("")
def chat(payload: ChatRequest) -> ChatResponse:
    use_bedrock = settings.bedrock_configured()
    if use_bedrock:
        result = bedrock_agent.run_bedrock_agent(payload.message)
        mode = "bedrock"
        if result.get("error"):
            reply = (f"Bedrock call failed ({result['error']}). "
                     "Set FOCUSFLOW_FORCE_MOCK=1 or add AWS credentials to use mock mode.")
            return ChatResponse(reply=reply, mode=mode,
                                actions=[AgentAction(tool="error", ok=False,
                                                     summary=result["error"])])
    else:
        result = mock_agent.run_mock_agent(payload.message)
        mode = "mock"

    actions = [
        AgentAction(tool=a.get("tool", "?"), ok=bool(a.get("ok")),
                    summary=str(a.get("summary", ""))[:500],
                    detail=_safe(a.get("detail", {})))
        for a in result.get("actions", [])
    ]
    return ChatResponse(
        reply=result.get("reply") or "Done.",
        mode=mode,
        actions=actions,
    )


@router.get("/mode")
def chat_mode():
    return {
        "mode": "bedrock" if settings.bedrock_configured() else "mock",
        "model": settings.bedrock_model_id if settings.bedrock_configured() else None,
        "region": settings.aws_region,
    }
