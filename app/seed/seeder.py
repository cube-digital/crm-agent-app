"""Seed a fresh tenant from db/fixtures.json.

On signup we copy *every* collection in the fixtures into the new tenant's
Postgres rows, re-namespacing all IDs to fresh UUIDs and rewriting every foreign
key + company_id so the tenant gets a fully isolated copy.

Stage handling: we keep all 18 `pipeline_stages` rows verbatim (identity lives in
`pipeline_stage_id`), because deals reference the duplicate stage rows. Funnel
ordering is resolved by label elsewhere (graph + ranking), not by de-duping here.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import (
    Activity,
    ActivityLink,
    Buyer,
    Contact,
    Deal,
    DealContact,
    Pipeline,
    PipelineStage,
)


@lru_cache
def _fixtures() -> dict:
    with open(get_settings().fixtures_path) as fh:
        return json.load(fh)


def _dt(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _amount(value) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def seed_tenant(db: Session, company_id: str) -> None:
    """Insert the full fixture dataset under `company_id` with fresh UUIDs."""
    data = _fixtures()

    # Single global old-id -> new-id map across every entity type.
    id_map: dict[str, str] = {}

    def new_id(old: str | None) -> str | None:
        if old is None:
            return None
        if old not in id_map:
            id_map[old] = str(uuid.uuid4())
        return id_map[old]

    # Pre-register every id so foreign keys always resolve regardless of order.
    for coll in (
        "pipelines",
        "pipeline_stages",
        "buyers",
        "contacts",
        "deals",
        "deal_contacts",
        "activities",
        "activity_links",
    ):
        for row in data.get(coll, []):
            new_id(row["id"])

    for p in data.get("pipelines", []):
        db.add(Pipeline(
            id=new_id(p["id"]), company_id=company_id, label=p.get("label", "Pipeline"),
            object_type=p.get("object_type"), display_order=p.get("display_order", 0),
            is_active=p.get("is_active", True),
        ))

    for s in data.get("pipeline_stages", []):
        db.add(PipelineStage(
            id=new_id(s["id"]), company_id=company_id, pipeline_id=new_id(s["pipeline_id"]),
            label=s.get("label", ""), display_order=s.get("display_order", 0),
        ))

    for b in data.get("buyers", []):
        db.add(Buyer(
            id=new_id(b["id"]), company_id=company_id, name=b.get("name", ""),
            description=b.get("description"), website_url=b.get("website_url"),
            linkedin_url=b.get("linkedin_url"), industry=b.get("industry"),
        ))

    for c in data.get("contacts", []):
        db.add(Contact(
            id=new_id(c["id"]), company_id=company_id, buyer_id=new_id(c.get("buyer_id")),
            name=c.get("name"), first_name=c.get("first_name"), last_name=c.get("last_name"),
            email=c.get("email"), phone=c.get("phone"), position=c.get("position"),
            linkedin_url=c.get("linkedin_url"),
        ))

    for d in data.get("deals", []):
        db.add(Deal(
            id=new_id(d["id"]), company_id=company_id,
            pipeline_id=new_id(d.get("pipeline_id")),
            pipeline_stage_id=new_id(d.get("pipeline_stage_id")),
            buyer_id=new_id(d.get("buyer_id")), deal_name=d.get("deal_name", "Untitled deal"),
            stage_label=d.get("stage_label"), deal_amount=_amount(d.get("deal_amount")),
            currency=d.get("currency"), deal_owner=d.get("deal_owner"),
            close_date=_dt(d.get("close_date")), is_closed=bool(d.get("is_closed")),
            is_closed_won=bool(d.get("is_closed_won")),
            source_created_at=_dt(d.get("source_created_at")),
            last_activity_at=_dt(d.get("last_activity_at")),
        ))

    for dc in data.get("deal_contacts", []):
        db.add(DealContact(
            id=new_id(dc["id"]), company_id=company_id, deal_id=new_id(dc["deal_id"]),
            contact_id=new_id(dc["contact_id"]), role=dc.get("role"),
            confidence=dc.get("confidence"),
        ))

    for a in data.get("activities", []):
        db.add(Activity(
            id=new_id(a["id"]), company_id=company_id, activity_type=a.get("activity_type"),
            subject=a.get("subject"), full_text=a.get("full_text"), direction=a.get("direction"),
            source=a.get("source"), timestamp=_dt(a.get("timestamp")),
        ))

    for al in data.get("activity_links", []):
        db.add(ActivityLink(
            id=new_id(al["id"]), company_id=company_id, activity_id=new_id(al["activity_id"]),
            entity_type=al.get("entity_type", "deal"), entity_id=new_id(al.get("entity_id")),
            confidence=al.get("confidence"),
        ))

    db.flush()
    _backfill_last_activity(db, company_id)


def _backfill_last_activity(db: Session, company_id: str) -> None:
    """`deals.last_activity_at` is null in the fixtures; compute it from the
    linked activity stream so the CRM and ranking have a real staleness signal."""
    rows = db.execute(
        select(ActivityLink.entity_id, func.max(Activity.timestamp))
        .join(Activity, Activity.id == ActivityLink.activity_id)
        .where(
            ActivityLink.company_id == company_id,
            ActivityLink.entity_type == "deal",
        )
        .group_by(ActivityLink.entity_id)
    ).all()
    for deal_id, last_ts in rows:
        deal = db.get(Deal, deal_id)
        if deal is not None and last_ts is not None:
            deal.last_activity_at = last_ts
    db.flush()
