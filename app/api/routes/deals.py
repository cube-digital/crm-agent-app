"""Deals + their activities, contacts, and the agent recommendation endpoint."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.graph_agent import run_recommendation
from app.agent.proactive import evaluate_deal_reactive, rank_open_deals, score_deal
from app.api.schemas import (
    ActivityCreate,
    ActivityOut,
    DealContactCreate,
    DealContactOut,
    DealContactRoleUpdate,
    DealCreate,
    DealOut,
    EvidenceItem,
    Page,
    RecommendationOut,
)
from app.auth.deps import Principal, get_db, get_principal, get_scoped_or_404
from app.db.models import Activity, ActivityLink, Contact, Deal, DealContact, PipelineStage, Recommendation

log = logging.getLogger("crm.deals")
router = APIRouter(prefix="/deals", tags=["deals"])


# --------------------------------------------------------------------------- #
# Deals CRUD
# --------------------------------------------------------------------------- #
@router.get("", response_model=Page)
def list_deals(limit: int = Query(50, le=200), offset: int = 0,
               principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    base = select(Deal).where(Deal.company_id == principal.company_id)
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    rows = db.scalars(base.order_by(Deal.updated_at.desc()).limit(limit).offset(offset))
    return Page(items=[DealOut.model_validate(d) for d in rows], total=total or 0,
                limit=limit, offset=offset)


@router.get("/{deal_id}", response_model=DealOut)
def get_deal(deal_id: str, principal: Principal = Depends(get_principal),
             db: Session = Depends(get_db)):
    return get_scoped_or_404(db, Deal, deal_id, principal)


@router.post("", response_model=DealOut, status_code=201)
def create_deal(body: DealCreate, principal: Principal = Depends(get_principal),
                db: Session = Depends(get_db)):
    data = body.model_dump(exclude_none=True)
    deal = Deal(company_id=principal.company_id, **data)
    if body.pipeline_stage_id:
        stage = _validate_stage(db, body.pipeline_stage_id, principal, deal.pipeline_id)
        deal.stage_label = stage.label
    db.add(deal)
    db.commit()
    return deal


@router.patch("/{deal_id}", response_model=DealOut)
def update_deal(deal_id: str, body: dict, principal: Principal = Depends(get_principal),
                db: Session = Depends(get_db)):
    deal = get_scoped_or_404(db, Deal, deal_id, principal)
    allowed = {"pipeline_stage_id", "deal_owner", "deal_amount", "close_date",
               "is_closed", "is_closed_won"}
    for k, v in body.items():
        if k not in allowed:
            continue
        if k == "pipeline_stage_id" and v is not None:
            stage = _validate_stage(db, v, principal, deal.pipeline_id)
            deal.stage_label = stage.label
        setattr(deal, k, v)
    db.commit()
    return deal


def _validate_stage(db: Session, stage_id: str, principal: Principal,
                    pipeline_id: str | None) -> PipelineStage:
    stage = db.get(PipelineStage, stage_id)
    if stage is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Stage not found")
    if stage.company_id != principal.company_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-tenant access denied")
    if pipeline_id is not None and stage.pipeline_id != pipeline_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Target stage does not belong to the deal's pipeline")
    return stage


# --------------------------------------------------------------------------- #
# Activities (timeline)
# --------------------------------------------------------------------------- #
@router.get("/{deal_id}/activities", response_model=Page)
def list_activities(deal_id: str, limit: int = Query(50, le=200), offset: int = 0,
                    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    get_scoped_or_404(db, Deal, deal_id, principal)
    base = (
        select(Activity)
        .join(ActivityLink, ActivityLink.activity_id == Activity.id)
        .where(
            ActivityLink.company_id == principal.company_id,
            ActivityLink.entity_type == "deal",
            ActivityLink.entity_id == deal_id,
        )
    )
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    rows = db.scalars(base.order_by(Activity.timestamp.desc().nulls_last()).limit(limit).offset(offset))
    return Page(items=[ActivityOut.model_validate(a) for a in rows], total=total or 0,
                limit=limit, offset=offset)


@router.post("/{deal_id}/activities", response_model=ActivityOut, status_code=201)
def create_activity(deal_id: str, body: ActivityCreate, background: BackgroundTasks,
                    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    """Core write path: create the activity + its deal link (Postgres only — the
    graph stays a static snapshot). Then re-evaluate the deal proactively."""
    deal = get_scoped_or_404(db, Deal, deal_id, principal)
    ts = body.timestamp or datetime.now(timezone.utc)
    activity = Activity(
        company_id=principal.company_id, activity_type=body.activity_type,
        subject=body.subject, full_text=body.full_text, direction=body.direction,
        source="crm", timestamp=ts,
    )
    db.add(activity)
    db.flush()
    db.add(ActivityLink(
        company_id=principal.company_id, activity_id=activity.id,
        entity_type="deal", entity_id=deal_id, confidence="confirmed",
    ))
    deal.last_activity_at = ts
    db.commit()

    # Reactive trigger: re-evaluate this deal in the background (note: the agent
    # reasons over the graph snapshot, which won't include this new activity
    # until /graph/rebuild — documented v1 limitation).
    background.add_task(evaluate_deal_reactive, principal.company_id, deal_id, deal.deal_name)
    return activity


# --------------------------------------------------------------------------- #
# Deal contacts
# --------------------------------------------------------------------------- #
@router.get("/{deal_id}/contacts", response_model=list[DealContactOut])
def list_deal_contacts(deal_id: str, principal: Principal = Depends(get_principal),
                       db: Session = Depends(get_db)):
    get_scoped_or_404(db, Deal, deal_id, principal)
    return list(db.scalars(
        select(DealContact).where(
            DealContact.company_id == principal.company_id, DealContact.deal_id == deal_id
        )
    ))


@router.post("/{deal_id}/contacts", response_model=DealContactOut, status_code=201)
def link_contact(deal_id: str, body: DealContactCreate,
                 principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    get_scoped_or_404(db, Deal, deal_id, principal)
    contact = get_scoped_or_404(db, Contact, body.contact_id, principal)
    dc = DealContact(
        company_id=principal.company_id, deal_id=deal_id, contact_id=contact.id,
        role=body.role or "unknown", confidence="manual",
    )
    db.add(dc)
    db.commit()
    return dc


@router.patch("/{deal_id}/contacts/{contact_id}", response_model=DealContactOut)
def update_deal_contact_role(deal_id: str, contact_id: str, body: DealContactRoleUpdate,
                             principal: Principal = Depends(get_principal),
                             db: Session = Depends(get_db)):
    dc = _get_deal_contact(db, deal_id, contact_id, principal)
    dc.role = body.role
    db.commit()
    return dc


@router.delete("/{deal_id}/contacts/{contact_id}", status_code=204)
def unlink_contact(deal_id: str, contact_id: str, principal: Principal = Depends(get_principal),
                   db: Session = Depends(get_db)):
    dc = _get_deal_contact(db, deal_id, contact_id, principal)
    db.delete(dc)
    db.commit()


def _get_deal_contact(db: Session, deal_id: str, contact_id: str,
                      principal: Principal) -> DealContact:
    dc = db.scalar(
        select(DealContact).where(
            DealContact.company_id == principal.company_id,
            DealContact.deal_id == deal_id,
            DealContact.contact_id == contact_id,
        )
    )
    if dc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Deal-contact link not found")
    return dc


# --------------------------------------------------------------------------- #
# Agent recommendation
# --------------------------------------------------------------------------- #
@router.post("/{deal_id}/recommendation", response_model=RecommendationOut)
def recommend(deal_id: str, principal: Principal = Depends(get_principal),
              db: Session = Depends(get_db)):
    deal = get_scoped_or_404(db, Deal, deal_id, principal)
    try:
        nba = run_recommendation(principal.company_id, deal_id)
    except Exception as exc:  # LLM unreachable / bad key / model error
        log.exception("Agent failed for deal %s", deal_id)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"Agent could not produce a recommendation: {exc}",
        )

    # Persist into the inbox (manual trigger), one row per deal.
    signals = {s["deal_id"]: s for s in rank_open_deals(principal.company_id)}
    score = signals.get(deal_id, {}).get("score", 0.0)
    for old in db.scalars(select(Recommendation).where(
        Recommendation.company_id == principal.company_id, Recommendation.deal_id == deal_id
    )):
        db.delete(old)
    if not nba.no_action:
        db.add(Recommendation(
            company_id=principal.company_id, deal_id=deal_id, deal_name=deal.deal_name,
            nba=nba.action, rationale=nba.rationale, urgency=nba.urgency, score=score,
            no_action=False, trigger_source="manual",
            evidence=[e.model_dump() for e in nba.evidence],
        ))
    db.commit()

    return RecommendationOut(
        deal_id=deal_id, deal_name=deal.deal_name, no_action=nba.no_action,
        nba=nba.action, rationale=nba.rationale, urgency=nba.urgency, score=score,
        evidence=[EvidenceItem(**e.model_dump()) for e in nba.evidence],
        trigger_source="manual",
    )
