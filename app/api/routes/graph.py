"""Drop + rebuild the current tenant's graph from Postgres."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.agent.enrich import enrich_tenant
from app.auth.deps import Principal, get_principal
from app.graph.build import build_graph

router = APIRouter(prefix="/graph", tags=["graph"])


@router.post("/rebuild")
def rebuild(principal: Principal = Depends(get_principal)) -> dict:
    """Idempotent: rebuilds only this tenant's graph key from Postgres (incl. any
    cached enrichment). LLM-free and deterministic."""
    counts = build_graph(principal.company_id)
    return {"status": "rebuilt", "company_id": principal.company_id, "counts": counts}


@router.post("/enrich")
def enrich(principal: Principal = Depends(get_principal)) -> dict:
    """(Re)generate the LLM enrichment for this tenant's deals (Haiku), cache it in
    Postgres, then rebuild the graph so nodes pick up the new attributes."""
    n = enrich_tenant(principal.company_id)
    counts = build_graph(principal.company_id)
    return {"status": "enriched", "deals_enriched": n, "counts": counts}
