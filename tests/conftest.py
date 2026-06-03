"""Shared test fixtures.

These are integration tests: they need Postgres + FalkorDB reachable (the same
infra `make up` brings online). They drive the real FastAPI app via TestClient,
which runs the startup lifespan (schema creation + scheduler). The scheduler's
first tick finds no tenants and then sleeps for the full interval, so it never
fires an LLM call during a short test run.
"""
from __future__ import annotations

import os
import uuid

# Disable the LLM bootstrap (enrich -> rebuild -> scan) that signup would otherwise
# run synchronously under TestClient. Must be set before app/config is imported.
os.environ.setdefault("BOOTSTRAP_ON_SIGNUP", "false")

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def signup(client: TestClient) -> dict:
    """Create a fresh tenant; returns the token payload."""
    email = f"user-{uuid.uuid4().hex[:8]}@example.com"
    res = client.post("/auth/signup", json={"email": email, "password": "secret123"})
    assert res.status_code == 200, res.text
    return res.json()


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
