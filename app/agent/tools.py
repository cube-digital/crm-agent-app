"""Agent tools — dynamic graph access.

Instead of fixed parameterised queries, the agent gets two tools and decides what
to retrieve:
  - get_graph_schema(): the node/edge/property catalog + example queries
  - run_cypher(query):  run READ-ONLY Cypher against THIS tenant's graph

Both are bound per request to the tenant's `company_id` (from the JWT) and the
focus `deal_id`. Reads go through FalkorDB's RO_QUERY mode, so writes are refused
server-side, and queries can only ever touch this tenant's graph key — scoping is
structural, not a filter the model could forget.
"""
from __future__ import annotations

import json
import logging

from langchain_core.tools import StructuredTool

from app.graph import schema as S
from app.graph.client import ro_query

log = logging.getLogger("crm.agent.tools")

_MAX_ROWS = 50


def _run_cypher(company_id: str, cypher: str) -> str:
    try:
        res = ro_query(company_id, cypher)
    except Exception as exc:  # surface the error so the agent can fix its query
        msg = str(exc)
        log.info("run_cypher ERROR: %s | query=%s", msg[:200], cypher[:300])
        return json.dumps({"error": msg[:400]})
    header = [h[1] if isinstance(h, (list, tuple)) else str(h) for h in (res.header or [])]
    rows = (res.result_set or [])[:_MAX_ROWS]
    truncated = len(res.result_set or []) > _MAX_ROWS
    log.info("run_cypher ok rows=%d query=%s", len(rows), cypher[:300])
    return json.dumps({"columns": header, "rows": rows, "truncated": truncated}, default=str)


def make_tools(company_id: str, deal_id: str) -> list[StructuredTool]:
    """Return the dynamic-Cypher tools, scoped to one tenant + focus deal."""

    def get_graph_schema() -> str:
        """Return the knowledge-graph schema (node labels, properties, edge types,
        and example Cypher). Call this FIRST so you know what you can query.
        The deal currently in focus has id '{deal_id}'."""
        return S.SCHEMA_DESCRIPTION + f"\n\nFOCUS DEAL id = '{deal_id}'"

    def run_cypher(query: str) -> str:
        """Run a READ-ONLY Cypher query against this tenant's knowledge graph and
        return the result rows as JSON ({columns, rows}). Writes are rejected.
        Use the schema from get_graph_schema. Inline literals (e.g. the focus deal
        id) directly in the query. On error, an {"error": ...} object is returned —
        read it and correct your query."""
        return _run_cypher(company_id, query)

    return [
        StructuredTool.from_function(func=get_graph_schema, name="get_graph_schema",
                                     description=get_graph_schema.__doc__),
        StructuredTool.from_function(func=run_cypher, name="run_cypher",
                                     description=run_cypher.__doc__),
    ]
