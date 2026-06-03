"""Recommendation logic.

Avoids depending on a live LLM: it tests the deterministic guarantees —
silence on closed deals, and that the graph layer yields evidence-grade data
(activity ids/subjects/timestamps) the agent can cite.
"""
from __future__ import annotations

from app.agent.graph_agent import run_recommendation
from app.graph import queries
from tests.conftest import auth, signup


def test_closed_deal_gets_no_action_without_llm(client):
    a = signup(client)
    company_id = a["company_id"]
    deals = client.get("/deals?limit=100", headers=auth(a["access_token"])).json()["items"]

    closed = [d for d in deals if d["is_closed"]]
    assert closed, "fixtures include closed deals (Licenseware/Transparent/FalkorDB)"

    # Short-circuits on is_closed -> no LLM call required.
    nba = run_recommendation(company_id, closed[0]["id"])
    assert nba.no_action is True
    assert not nba.evidence


def test_graph_provides_citable_evidence_for_open_deal(client):
    a = signup(client)
    company_id = a["company_id"]
    deals = client.get("/deals?limit=100", headers=auth(a["access_token"])).json()["items"]

    open_deals = [d for d in deals if not d["is_closed"]]
    assert open_deals

    # The graph-backed tools return real activity ids the agent can cite.
    acts = queries.recent_activities(company_id, open_deals[0]["id"], limit=5)
    assert acts, "open seeded deals have activities"
    assert acts[0]["activity_id"]
    assert "timestamp" in acts[0]

    # Silence signal is computed from the snapshot against real now().
    silence = queries.silent_period(company_id, open_deals[0]["id"])
    assert "days_since_last_activity" in silence
