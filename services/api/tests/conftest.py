"""Pytest fixtures: sqlite-backed test DB + TestClient.

DATABASE_URL is forced to a temp sqlite file BEFORE any app import so the
lazy engine binds to it. The TestClient triggers the lifespan, which runs
init_db() and creates the tables.
"""

from __future__ import annotations

import os
import tempfile

# Must run before importing app modules.
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["LLM_PROVIDER"] = "mock"

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c
