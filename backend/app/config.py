"""Environment-driven configuration. No secrets are ever hardcoded."""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
load_dotenv(BACKEND_DIR.parent / ".env")


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


class Settings:
    app_name: str = "FocusFlow"
    db_path: str = os.getenv("FOCUSFLOW_DB_PATH", str(BACKEND_DIR / "data" / "focusflow.db"))
    seed_demo: bool = _bool("FOCUSFLOW_SEED_DEMO", True)

    # Deterministic scheduling window (local time)
    work_start: int = int(os.getenv("FOCUSFLOW_WORK_START", "9"))
    work_end: int = int(os.getenv("FOCUSFLOW_WORK_END", "18"))
    schedule_horizon_days: int = int(os.getenv("FOCUSFLOW_HORIZON_DAYS", "14"))

    # AWS / Bedrock
    aws_region: str = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
    bedrock_model_id: str = os.getenv(
        "FOCUSFLOW_BEDROCK_MODEL_ID", "anthropic.claude-sonnet-4-20250514-v1:0"
    )
    force_mock: bool = _bool("FOCUSFLOW_FORCE_MOCK", False)

    # CORS origins for the Next.js frontend
    cors_origins: list[str] = [
        o.strip()
        for o in os.getenv(
            "FOCUSFLOW_CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000,"
            "http://localhost:3001,http://127.0.0.1:3001",
        ).split(",")
        if o.strip()
    ]
    # Also accept loopback and private-LAN origins (the dev UI can be opened via LAN IP)
    cors_origin_regex: str = os.getenv(
        "FOCUSFLOW_CORS_ORIGIN_REGEX",
        r"^https?://(localhost|127\.0\.0\.1|0\.0\.0\.0"
        r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
        r"|192\.168\.\d{1,3}\.\d{1,3}"
        r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(?::\d{1,5})?$",
    )

    # MCP server
    mcp_host: str = os.getenv("FOCUSFLOW_MCP_HOST", "127.0.0.1")
    mcp_port: int = int(os.getenv("FOCUSFLOW_MCP_PORT", "8001"))

    def bedrock_configured(self) -> bool:
        if self.force_mock:
            return False
        return bool(os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY")) or bool(
            os.getenv("AWS_PROFILE")
        )


settings = Settings()
