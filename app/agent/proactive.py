"""Proactivity: a real trigger, not just an endpoint.

Two mechanisms write to the `recommendations` inbox; `GET /proactive/feed` only
*reads* it — proving the work happened on a trigger:

1. **Scheduled scan** — a background asyncio task wakes every
   PROACTIVE_SCAN_INTERVAL_SECONDS, ranks each enabled tenant's open deals by a
   cheap graph-backed signal score, and runs the agent on the top N.
2. **Reactive** — when a new activity is created on a deal, that deal is
   re-evaluated immediately (see routes/deals.py).

Closed deals are skipped. The off switch is the per-tenant
`Company.proactive_enabled` flag (POST /proactive/{enabled}).
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.agent.graph_agent import run_recommendation
from app.config import get_settings
from app.db.models import Company, Recommendation
from app.db.session import SessionLocal
from app.graph import queries

log = logging.getLogger("crm.proactive")


# --------------------------------------------------------------------------- #
# Ranking (cheap, graph-backed — no LLM)
# --------------------------------------------------------------------------- #
def score_deal(signal: dict) -> float:
    """Higher = more in need of attention.

    Deal size is unusable (all zero) so we rank on **silence × stage progression**:
    a deal that has gone quiet matters more the further it is down the funnel.
    Deals with no recorded activity are treated as maximally stale.
    """
    days = signal.get("days_since_last_activity")
    silence = 60.0 if days is None else float(days)
    stage_idx = max(signal.get("stage_order_index", -1), 0)
    return round(silence * (1.0 + 0.15 * stage_idx), 2)


def rank_open_deals(company_id: str) -> list[dict]:
    deals = queries.open_deals_with_signals(company_id)
    for d in deals:
        d["score"] = score_deal(d)
    return sorted(deals, key=lambda d: d["score"], reverse=True)


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
def _store(company_id: str, deal_id: str, deal_name: str | None, score: float,
           trigger_source: str) -> None:
    """Run the agent for one deal and upsert the result into the inbox."""
    nba = run_recommendation(company_id, deal_id)
    db = SessionLocal()
    try:
        # One recommendation per deal: clear the previous one first.
        for old in db.scalars(
            select(Recommendation).where(
                Recommendation.company_id == company_id,
                Recommendation.deal_id == deal_id,
            )
        ):
            db.delete(old)

        if not nba.no_action:
            db.add(Recommendation(
                company_id=company_id, deal_id=deal_id, deal_name=deal_name,
                nba=nba.action, rationale=nba.rationale, urgency=nba.urgency,
                score=score, no_action=False, trigger_source=trigger_source,
                evidence=[e.model_dump() for e in nba.evidence],
            ))
        db.commit()
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Triggers
# --------------------------------------------------------------------------- #
def run_scan_for_tenant(company_id: str, top_n: int | None = None) -> int:
    """Rank open deals and evaluate the top N. Returns # of deals evaluated."""
    top_n = top_n or get_settings().proactive_top_n
    ranked = rank_open_deals(company_id)[:top_n]
    log.info("Proactive scan tenant=%s evaluating %d deals", company_id, len(ranked))
    for d in ranked:
        try:
            _store(company_id, d["deal_id"], d["deal_name"], d["score"], "scheduled")
        except Exception:
            log.exception("Scan failed for deal %s", d["deal_id"])
    return len(ranked)


def evaluate_deal_reactive(company_id: str, deal_id: str, deal_name: str | None = None) -> None:
    """Re-evaluate a single deal after a change (new activity). Best-effort."""
    try:
        signals = {s["deal_id"]: s for s in queries.open_deals_with_signals(company_id)}
        score = score_deal(signals.get(deal_id, {})) if deal_id in signals else 0.0
        _store(company_id, deal_id, deal_name, score, "reactive")
    except Exception:
        log.exception("Reactive evaluation failed for deal %s", deal_id)


def _tenants_with_proactive() -> list[str]:
    db = SessionLocal()
    try:
        return list(db.scalars(select(Company.id).where(Company.proactive_enabled.is_(True))))
    finally:
        db.close()


async def scheduler_loop(stop: asyncio.Event) -> None:
    """Background morning-brief scanner. Runs until `stop` is set."""
    interval = get_settings().proactive_scan_interval_seconds
    log.info("Proactive scheduler started (interval=%ss)", interval)
    while not stop.is_set():
        try:
            for company_id in _tenants_with_proactive():
                await asyncio.to_thread(run_scan_for_tenant, company_id)
        except Exception:
            log.exception("Scheduler tick failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
    log.info("Proactive scheduler stopped")
