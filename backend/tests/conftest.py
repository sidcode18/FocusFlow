"""Shared test fixtures: isolated temp DB, clean tables, FastAPI TestClient."""
import os
import tempfile
from pathlib import Path

import pytest

_TMP = tempfile.mkdtemp(prefix="focusflow_test_")
os.environ["FOCUSFLOW_DB_PATH"] = str(Path(_TMP) / "test.db")
os.environ["FOCUSFLOW_SEED_DEMO"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from app.db import get_conn, init_db  # noqa: E402


@pytest.fixture()
def clean_db():
    """Empty database for the current test."""
    init_db()
    with get_conn() as conn:
        conn.execute("DELETE FROM schedule_blocks")
        conn.execute("DELETE FROM tasks")
    yield


@pytest.fixture()
def client(clean_db):
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def seeded_client(client):
    """Client with realistic demo data seeded."""
    from app.seed import seed

    seed()
    yield client
