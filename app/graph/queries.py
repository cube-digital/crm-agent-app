"""Parameterised Cypher read queries against a tenant's graph.

These are the *only* graph reads the agent tools rely on. Each function takes the
tenant `company_id` (from the JWT) and returns plain Python dicts/lists — no graph
objects leak upward. "Days since" values are computed against real `now()` from
the snapshot timestamps, so staleness stays correct even though the graph is
static.
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


def recent_activities(company_id: str, deal_id: str, limit: int = 10) -> list[dict]:
    cy = (
        f"MATCH (a:{S.ACTIVITY})-[:{S.ON_DEAL}]->(d:{S.DEAL} {{id:$id}}) "
        "RETURN a.id, a.type, a.subject, a.direction, a.timestamp, a.snippet "
        "ORDER BY a.ts DESC LIMIT $limit"
    )
    rows = _rows(query(company_id, cy, {"id": deal_id, "limit": int(limit)}))
    return [
        {"activity_id": r[0], "type": r[1], "subject": r[2],
         "direction": r[3], "timestamp": r[4], "snippet": r[5]}
        for r in rows
    ]


def silent_period(company_id: str, deal_id: str) -> dict:
    def _last(direction_filter: str) -> str | None:
        cy = (
            f"MATCH (a:{S.ACTIVITY})-[:{S.ON_DEAL}]->(d:{S.DEAL} {{id:$id}}) "
            f"{direction_filter} RETURN a.timestamp ORDER BY a.ts DESC LIMIT 1"
        )
        rows = _rows(query(company_id, cy, {"id": deal_id}))
        return rows[0][0] if rows else None

    last_any = _last("")
    last_in = _last("WHERE a.direction = 'inbound'")
    last_out = _last("WHERE a.direction = 'outbound'")
    return {
        "last_activity_at": last_any,
        "last_inbound_at": last_in,
        "last_outbound_at": last_out,
        "days_since_last_activity": _days_since(last_any),
        "days_since_last_inbound": _days_since(last_in),
        "days_since_last_outbound": _days_since(last_out),
    }


def stakeholder_map(company_id: str, deal_id: str) -> list[dict]:
    cy = (
        f"MATCH (c:{S.CONTACT})-[r:{S.INVOLVED_IN}]->(d:{S.DEAL} {{id:$id}}) "
        "RETURN c.name, c.email, c.position, r.role, r.confidence"
    )
    rows = _rows(query(company_id, cy, {"id": deal_id}))
    return [
        {"name": r[0], "email": r[1], "position": r[2], "role": r[3], "confidence": r[4]}
        for r in rows
    ]


def stage_context(company_id: str, deal_id: str) -> dict:
    cy = (
        f"MATCH (d:{S.DEAL} {{id:$id}})-[:{S.IN_STAGE}]->(s:{S.STAGE}) "
        f"OPTIONAL MATCH (s)-[:{S.NEXT}]->(nxt:{S.STAGE}) "
        "RETURN s.label, s.order_index, nxt.label"
    )
    rows = _rows(query(company_id, cy, {"id": deal_id}))
    if not rows:
        return {"stage_label": None, "order_index": -1, "next_stage": None, "is_terminal": False}
    r = rows[0]
    return {
        "stage_label": r[0],
        "order_index": r[1] if r[1] is not None else -1,
        "next_stage": r[2],
        "is_terminal": (r[0] in S.TERMINAL_STAGES),
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
