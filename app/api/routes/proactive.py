"""Proactive feed (read the inbox) + the per-tenant off switch."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import EvidenceItem, RecommendationOut
from app.auth.deps import Principal, get_db, get_principal
from app.db.models import Company, Recommendation

router = APIRouter(prefix="/proactive", tags=["proactive"])

_TRUE = {"true", "1", "on", "yes", "enabled"}
_FALSE = {"false", "0", "off", "no", "disabled"}


@router.get("/feed", response_model=list[RecommendationOut])
def feed(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    """Ranked deals needing action now — precomputed by the proactive triggers."""
    rows = db.scalars(
        select(Recommendation)
        .where(Recommendation.company_id == principal.company_id,
               Recommendation.no_action.is_(False))
        .order_by(Recommendation.score.desc())
    )
    return [
        RecommendationOut(
            deal_id=r.deal_id, deal_name=r.deal_name, no_action=r.no_action,
            nba=r.nba, rationale=r.rationale, urgency=r.urgency, score=r.score,
            evidence=[EvidenceItem(**e) for e in (r.evidence or [])],
            trigger_source=r.trigger_source, created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("/{enabled}")
def toggle(enabled: str, principal: Principal = Depends(get_principal),
           db: Session = Depends(get_db)) -> dict:
    val = enabled.strip().lower()
    if val in _TRUE:
        flag = True
    elif val in _FALSE:
        flag = False
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Use true/false")
    company = db.get(Company, principal.company_id)
    company.proactive_enabled = flag
    db.commit()
    return {"proactive_enabled": flag}
