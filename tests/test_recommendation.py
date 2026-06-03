"""Recommendation + graph-access logic.

Avoids a live LLM: tests the deterministic guarantees — silence on closed deals,
that the graph exposes citable data via the agent's read-only Cypher path, and
that writes are refused.
"""
from __future__ import annotations

import pytest

from app.agent.graph_agent import run_recommendation
from app.graph.client import ro_query
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


def test_agent_cypher_path_reads_evidence(client):
    a = signup(client)
    company_id = a["company_id"]
    deals = client.get("/deals?limit=100", headers=auth(a["access_token"])).json()["items"]
    open_deals = [d for d in deals if not d["is_closed"]]
    assert open_deals
    deal_id = open_deals[0]["id"]

    # The agent authors Cypher; the read-only path returns real activity ids.
    res = ro_query(
        company_id,
        "MATCH (act:Activity)-[:ON_DEAL]->(:Deal {id:$id}) "
        "RETURN act.id, act.subject, act.timestamp ORDER BY act.ts DESC LIMIT 3",
        {"id": deal_id},
    )
    assert res.result_set, "open seeded deals have activities reachable via Cypher"
    assert res.result_set[0][0]  # activity id present


def test_agent_cypher_is_read_only(client):
    a = signup(client)
    company_id = a["company_id"]
    # Writes must be rejected by FalkorDB's RO_QUERY mode.
    with pytest.raises(Exception):
        ro_query(company_id, "CREATE (:Injected {x: 1})")
