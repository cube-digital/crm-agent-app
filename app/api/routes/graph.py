"""Drop + rebuild the current tenant's graph from Postgres."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth.deps import Principal, get_principal
from app.graph.build import build_graph

router = APIRouter(prefix="/graph", tags=["graph"])


@router.post("/rebuild")
def rebuild(principal: Principal = Depends(get_principal)) -> dict:
    """Idempotent: rebuilds only this tenant's graph key, never another's."""
    counts = build_graph(principal.company_id)
    return {"status": "rebuilt", "company_id": principal.company_id, "counts": counts}
