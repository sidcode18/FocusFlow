"""FocusFlow FastAPI application entry point.

Run:  uvicorn app.main:app --port 8000   (from the backend/ directory)
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import init_db
from app.routers import chat, schedule, tasks
from app.seed import ensure_seeded

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    result = ensure_seeded()
    if result.get("seeded"):
        logging.getLogger(__name__).info(
            "Seeded demo data: %s tasks, %s schedule blocks",
            result["created"], result["scheduled"],
        )
    yield


app = FastAPI(title="FocusFlow API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router)
app.include_router(schedule.router)
app.include_router(chat.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "FocusFlow API", "version": "1.0.0"}
