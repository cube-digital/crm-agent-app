"""Parameterised Cypher reads used by *internal app logic* (not the agent).

The agent now authors its own Cypher via the run_cypher tool. These two helpers
back the closed-deal short-circuit (deal_overview) and the proactive ranking
(open_deals_with_signals). "Days since" is computed against real `now()` from the
snapshot timestamps, so staleness stays correct even though the graph is static.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.graph import schema as S
from app.graph.client import query


def _rows(result) -> list[list]:
    return result.result_set or []


def _days_since(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return round((datetime.now(timezone.utc) - dt).total_seconds() / 86400, 1)


def deal_exists(company_id: str, deal_id: str) -> bool:
    res = query(company_id, f"MATCH (d:{S.DEAL} {{id:$id}}) RETURN count(d)", {"id": deal_id})
    rows = _rows(res)
    return bool(rows and rows[0][0])


def deal_overview(company_id: str, deal_id: str) -> dict | None:
    cy = (
        f"MATCH (d:{S.DEAL} {{id:$id}}) "
        f"OPTIONAL MATCH (d)-[:{S.WITH_BUYER}]->(b:{S.BUYER}) "
        f"OPTIONAL MATCH (d)-[:{S.IN_STAGE}]->(s:{S.STAGE}) "
        f"OPTIONAL MATCH (c:{S.CONTACT})-[:{S.INVOLVED_IN}]->(d) "
        "RETURN d.name, d.stage_label, d.is_closed, d.is_closed_won, d.owner, "
        "d.activity_count, d.inbound_count, d.outbound_count, "
        "d.first_activity_at, d.last_activity_at, "
        "b.name, s.order_index, count(DISTINCT c)"
    )
    rows = _rows(query(company_id, cy, {"id": deal_id}))
    if not rows:
        return None
    r = rows[0]
    return {
        "deal_id": deal_id,
        "deal_name": r[0],
        "stage_label": r[1],
        "is_closed": bool(r[2]),
        "is_closed_won": bool(r[3]),
        "owner": r[4],
        "activity_count": r[5] or 0,
        "inbound_count": r[6] or 0,
        "outbound_count": r[7] or 0,
        "first_activity_at": r[8],
        "last_activity_at": r[9],
        "buyer_name": r[10],
        "stage_order_index": r[11] if r[11] is not None else -1,
        "contact_count": r[12] or 0,
        "days_since_last_activity": _days_since(r[9]),
        "is_terminal": (r[1] in S.TERMINAL_STAGES),
    }


def open_deals_with_signals(company_id: str) -> list[dict]:
    """For proactive ranking: every non-closed deal with its staleness signals."""
    cy = (
        f"MATCH (d:{S.DEAL}) WHERE d.is_closed = false "
        "RETURN d.id, d.name, d.stage_label, d.activity_count, "
        "d.inbound_count, d.outbound_count, d.last_activity_at"
    )
    rows = _rows(query(company_id, cy))
    out = []
    for r in rows:
        out.append({
            "deal_id": r[0], "deal_name": r[1], "stage_label": r[2],
            "activity_count": r[3] or 0, "inbound_count": r[4] or 0,
            "outbound_count": r[5] or 0, "last_activity_at": r[6],
            "days_since_last_activity": _days_since(r[6]),
            "stage_order_index": S.stage_index(r[2]),
        })
    return out
