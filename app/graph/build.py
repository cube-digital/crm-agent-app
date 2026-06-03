"""Build (or rebuild) a tenant's knowledge graph from Postgres.

The graph is a **static snapshot** of the tenant's relational data, built at
signup and re-buildable via /graph/rebuild. CRM writes after the build do NOT
propagate (documented v1 limitation) — rebuild to refresh.

This is the only module that reads Postgres *to write the graph*. The agent's
tools read the graph only.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Activity,
    ActivityLink,
    Buyer,
    Contact,
    Deal,
    DealContact,
    DealEnrichment,
    PipelineStage,
)
from app.db.session import SessionLocal
from app.graph import schema as S
from app.graph.client import drop_graph, tenant_graph

log = logging.getLogger("crm.graph.build")

_TAG_RE = re.compile(r"<[^>]+>")


def _snippet(text: str | None, limit: int = 280) -> str:
    """Strip HTML tags + collapse whitespace; truncate for evidence display."""
    if not text:
        return ""
    clean = _TAG_RE.sub(" ", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:limit]


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _epoch(dt: datetime | None) -> float | None:
    return dt.timestamp() if dt else None


def build_graph(company_id: str) -> dict:
    """Drop and rebuild the tenant graph. Returns node/edge counts."""
    db: Session = SessionLocal()
    try:
        return _build(db, company_id)
    finally:
        db.close()


def _build(db: Session, company_id: str) -> dict:
    drop_graph(company_id)
    g = tenant_graph(company_id)

    # ---- Stages (deduped by label) + funnel NEXT edges -------------------- #
    stage_labels = {
        s.label for s in db.scalars(
            select(PipelineStage).where(PipelineStage.company_id == company_id)
        )
    }
    for label in stage_labels:
        g.query(
            f"CREATE (:{S.STAGE} {{label:$label, order_index:$idx}})",
            {"label": label, "idx": S.stage_index(label)},
        )
    for a, b in zip(S.FUNNEL_PATH, S.FUNNEL_PATH[1:]):
        if a in stage_labels and b in stage_labels:
            g.query(
                f"MATCH (x:{S.STAGE} {{label:$a}}),(y:{S.STAGE} {{label:$b}}) "
                f"CREATE (x)-[:{S.NEXT}]->(y)",
                {"a": a, "b": b},
            )

    # ---- Buyers ----------------------------------------------------------- #
    buyers = list(db.scalars(select(Buyer).where(Buyer.company_id == company_id)))
    if buyers:
        g.query(
            f"UNWIND $rows AS r CREATE (:{S.BUYER} {{id:r.id, name:r.name, industry:r.industry}})",
            {"rows": [{"id": b.id, "name": b.name, "industry": b.industry} for b in buyers]},
        )

    # ---- Contacts + WORKS_AT --------------------------------------------- #
    contacts = list(db.scalars(select(Contact).where(Contact.company_id == company_id)))
    if contacts:
        g.query(
            f"UNWIND $rows AS r CREATE (:{S.CONTACT} "
            "{id:r.id, name:r.name, email:r.email, position:r.position, buyer_id:r.buyer_id})",
            {"rows": [
                {"id": c.id, "name": c.name, "email": c.email,
                 "position": c.position, "buyer_id": c.buyer_id}
                for c in contacts
            ]},
        )
        g.query(
            f"MATCH (c:{S.CONTACT}),(b:{S.BUYER}) WHERE c.buyer_id = b.id "
            f"CREATE (c)-[:{S.WORKS_AT}]->(b)"
        )

    # ---- Per-deal activity aggregates (computed here, queried cheaply) ---- #
    links = list(db.scalars(
        select(ActivityLink).where(
            ActivityLink.company_id == company_id, ActivityLink.entity_type == "deal"
        )
    ))
    acts = {a.id: a for a in db.scalars(select(Activity).where(Activity.company_id == company_id))}
    deal_acts: dict[str, list[Activity]] = {}
    for link in links:
        act = acts.get(link.activity_id)
        if act is not None:
            deal_acts.setdefault(link.entity_id, []).append(act)

    # ---- LLM enrichment (cached in Postgres; copied onto Deal nodes) ----- #
    enrich = {
        e.deal_id: e for e in db.scalars(
            select(DealEnrichment).where(DealEnrichment.company_id == company_id)
        )
    }

    # ---- Deals + WITH_BUYER + IN_STAGE ----------------------------------- #
    deals = list(db.scalars(select(Deal).where(Deal.company_id == company_id)))
    deal_rows = []
    for d in deals:
        da = deal_acts.get(d.id, [])
        ts = [a.timestamp for a in da if a.timestamp]
        e = enrich.get(d.id)
        deal_rows.append({
            "id": d.id, "name": d.deal_name, "stage_label": d.stage_label,
            "is_closed": bool(d.is_closed), "is_closed_won": bool(d.is_closed_won),
            "owner": d.deal_owner, "buyer_id": d.buyer_id,
            "activity_count": len(da),
            "inbound_count": sum(1 for a in da if a.direction == "inbound"),
            "outbound_count": sum(1 for a in da if a.direction == "outbound"),
            "first_activity_at": _iso(min(ts)) if ts else None,
            "last_activity_at": _iso(max(ts)) if ts else None,
            # Enriched attributes (empty strings if enrichment hasn't run yet).
            "summary": (e.summary if e else "") or "",
            "sentiment": (e.sentiment if e else "") or "",
            "key_topics": "; ".join(e.key_topics) if e and e.key_topics else "",
            "open_asks": "; ".join(e.open_asks) if e and e.open_asks else "",
        })
    if deal_rows:
        g.query(
            f"UNWIND $rows AS r CREATE (:{S.DEAL} {{"
            "id:r.id, name:r.name, stage_label:r.stage_label, is_closed:r.is_closed, "
            "is_closed_won:r.is_closed_won, owner:r.owner, buyer_id:r.buyer_id, "
            "activity_count:r.activity_count, inbound_count:r.inbound_count, "
            "outbound_count:r.outbound_count, first_activity_at:r.first_activity_at, "
            "last_activity_at:r.last_activity_at, summary:r.summary, sentiment:r.sentiment, "
            "key_topics:r.key_topics, open_asks:r.open_asks})",
            {"rows": deal_rows},
        )
        g.query(
            f"MATCH (d:{S.DEAL}),(b:{S.BUYER}) WHERE d.buyer_id = b.id "
            f"CREATE (d)-[:{S.WITH_BUYER}]->(b)"
        )
        g.query(
            f"MATCH (d:{S.DEAL}),(s:{S.STAGE}) WHERE d.stage_label = s.label "
            f"CREATE (d)-[:{S.IN_STAGE}]->(s)"
        )

    # ---- INVOLVED_IN (deal_contacts) ------------------------------------- #
    dcs = list(db.scalars(select(DealContact).where(DealContact.company_id == company_id)))
    if dcs:
        g.query(
            f"UNWIND $rows AS r MATCH (c:{S.CONTACT} {{id:r.contact_id}}),(d:{S.DEAL} {{id:r.deal_id}}) "
            f"CREATE (c)-[:{S.INVOLVED_IN} {{role:r.role, confidence:r.confidence}}]->(d)",
            {"rows": [
                {"contact_id": dc.contact_id, "deal_id": dc.deal_id,
                 "role": dc.role, "confidence": dc.confidence}
                for dc in dcs
            ]},
        )

    # ---- Activities + ON_DEAL -------------------------------------------- #
    act_rows = []
    for link in links:
        act = acts.get(link.activity_id)
        if act is None:
            continue
        act_rows.append({
            "id": act.id, "deal_id": link.entity_id, "type": act.activity_type,
            "subject": act.subject, "direction": act.direction or "unknown",
            "timestamp": _iso(act.timestamp), "ts": _epoch(act.timestamp) or 0.0,
            "snippet": _snippet(act.full_text),
        })
    if act_rows:
        g.query(
            f"UNWIND $rows AS r MATCH (d:{S.DEAL} {{id:r.deal_id}}) "
            f"CREATE (a:{S.ACTIVITY} {{id:r.id, type:r.type, subject:r.subject, "
            "direction:r.direction, timestamp:r.timestamp, ts:r.ts, snippet:r.snippet})"
            f"-[:{S.ON_DEAL} {{direction:r.direction, ts:r.ts}}]->(d)",
            {"rows": act_rows},
        )

    counts = {
        "stages": len(stage_labels), "buyers": len(buyers), "contacts": len(contacts),
        "deals": len(deals), "deal_contacts": len(dcs), "activities": len(act_rows),
    }
    log.info("Graph built for tenant %s: %s", company_id, counts)
    return counts
