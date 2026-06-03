"""Liveness — 200 when app + Postgres + FalkorDB are reachable."""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.db.session import engine
from app.graph.client import ping as graph_ping

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    db_ok = True
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    graph_ok = graph_ping()
    status = "ok" if (db_ok and graph_ok) else "degraded"
    return {"status": status, "postgres": db_ok, "falkordb": graph_ok}
