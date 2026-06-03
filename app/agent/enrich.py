"""LLM enrichment pass: derive per-deal attributes once and cache them in Postgres.

This runs at seed time (and on demand). The graph build copies these attributes
onto the Deal nodes, so `/graph/rebuild` never needs the LLM. Uses the fast model
(Haiku) since this is a bulk pass over every deal.

Derived attributes (the "exploded" node attributes):
  - summary     : a digest of the deal thread + current state
  - sentiment   : positive | neutral | negative | at_risk
  - key_topics  : the main things being discussed
  - open_asks   : concrete buyer requests we haven't answered
"""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.graph_agent import get_model
from app.config import get_settings
from app.db.models import Activity, ActivityLink, Deal, DealEnrichment
from app.db.session import SessionLocal

log = logging.getLogger("crm.enrich")

_TAG_RE = re.compile(r"<[^>]+>")


class _Enrichment(BaseModel):
    summary: str = Field(description="2-4 sentence digest of the deal: where it stands, "
                                     "what's happened, what the buyer wants.")
    sentiment: str = Field(description="One of: positive, neutral, negative, at_risk")
    key_topics: list[str] = Field(default_factory=list,
                                  description="Main topics discussed (max ~6 short phrases).")
    open_asks: list[str] = Field(default_factory=list,
                                 description="Concrete buyer requests not yet fulfilled (may be empty).")


_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You summarise a sales deal from its activity timeline. Be factual and grounded "
     "in the activities provided; do not invent specifics. Keep it concise."),
    ("human",
     "Deal: {deal_name} (stage: {stage}). Recent activities (newest first):\n\n{timeline}\n\n"
     "Produce the structured enrichment."),
])


def _clean(text: str | None, limit: int = 600) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", text)).strip()[:limit]


def _deal_timeline(db: Session, company_id: str, deal_id: str, limit: int = 20) -> str:
    rows = db.execute(
        select(Activity)
        .join(ActivityLink, ActivityLink.activity_id == Activity.id)
        .where(ActivityLink.company_id == company_id,
               ActivityLink.entity_type == "deal", ActivityLink.entity_id == deal_id)
        .order_by(Activity.timestamp.desc().nulls_last())
        .limit(limit)
    ).scalars().all()
    lines = []
    for a in rows:
        ts = a.timestamp.date().isoformat() if a.timestamp else "?"
        direction = a.direction or "unknown"
        lines.append(f"- [{ts}] {a.activity_type}/{direction}: {a.subject or '(no subject)'} "
                     f"— {_clean(a.full_text, 240)}")
    return "\n".join(lines) or "(no activities)"


def generate_for_deal(db: Session, company_id: str, deal: Deal) -> _Enrichment:
    model = get_model(get_settings().proactive_model).with_structured_output(_Enrichment)
    timeline = _deal_timeline(db, company_id, deal.id)
    chain = _PROMPT | model
    return chain.invoke({
        "deal_name": deal.deal_name, "stage": deal.stage_label or "unknown", "timeline": timeline,
    })


def _upsert(company_id: str, deal_id: str, e: _Enrichment, model_name: str) -> None:
    db = SessionLocal()
    try:
        row = db.scalar(select(DealEnrichment).where(DealEnrichment.deal_id == deal_id))
        if row is None:
            row = DealEnrichment(company_id=company_id, deal_id=deal_id)
            db.add(row)
        row.summary = e.summary
        row.sentiment = e.sentiment
        row.key_topics = e.key_topics
        row.open_asks = e.open_asks
        row.model = model_name
        db.commit()
    finally:
        db.close()


def enrich_tenant(company_id: str) -> int:
    """Generate + cache enrichment for every deal in the tenant. Returns # enriched."""
    model_name = get_settings().proactive_model
    db = SessionLocal()
    try:
        deals = list(db.scalars(select(Deal).where(Deal.company_id == company_id)))
    finally:
        db.close()

    def _one(deal: Deal) -> bool:
        d = SessionLocal()
        try:
            e = generate_for_deal(d, company_id, deal)
        except Exception:
            log.exception("Enrichment failed for deal %s", deal.id)
            return False
        finally:
            d.close()
        _upsert(company_id, deal.id, e, model_name)
        return True

    log.info("Enriching %d deals for tenant %s (model=%s)", len(deals), company_id, model_name)
    if not deals:
        return 0
    with ThreadPoolExecutor(max_workers=min(4, len(deals))) as ex:
        results = list(ex.map(_one, deals))
    n = sum(1 for r in results if r)
    log.info("Enriched %d/%d deals for tenant %s", n, len(deals), company_id)
    return n
