"""FalkorDB connection + per-tenant graph handles.

Multi-tenancy in the graph: one graph **key per tenant**, named
``{prefix}:{company_id}``. A tenant's subgraph is physically separate, so a query
issued against tenant A's key can never touch tenant B's data — isolation is
structural, not a WHERE clause we might forget. The company_id always comes from
the JWT, never from the request body.
"""
from __future__ import annotations

from functools import lru_cache

from falkordb import FalkorDB

from app.config import get_settings


@lru_cache
def _client() -> FalkorDB:
    s = get_settings()
    kwargs: dict = {"host": s.falkordb_host, "port": s.falkordb_port}
    if s.falkordb_username:
        kwargs["username"] = s.falkordb_username
    if s.falkordb_password:
        kwargs["password"] = s.falkordb_password
    return FalkorDB(**kwargs)


def graph_key(company_id: str) -> str:
    return f"{get_settings().falkordb_graph}:{company_id}"


def tenant_graph(company_id: str):
    """Return the FalkorDB Graph handle for a tenant."""
    return _client().select_graph(graph_key(company_id))


def query(company_id: str, cypher: str, params: dict | None = None):
    """Run a parameterised Cypher query against a tenant's graph."""
    return tenant_graph(company_id).query(cypher, params or {})


def ro_query(company_id: str, cypher: str, params: dict | None = None):
    """Run a READ-ONLY Cypher query (FalkorDB rejects writes server-side).

    Used for agent-authored queries: structurally scoped to the tenant's graph
    key, and writes (CREATE/SET/DELETE/MERGE/…) are refused by GRAPH.RO_QUERY.
    """
    return tenant_graph(company_id).ro_query(cypher, params or {})


def drop_graph(company_id: str) -> None:
    """Delete a tenant's graph if it exists (safe to call when absent)."""
    try:
        tenant_graph(company_id).delete()
    except Exception:
        # FalkorDB raises if the key doesn't exist yet — that's fine for a rebuild.
        pass


def ping() -> bool:
    """Liveness check for /health."""
    try:
        _client().connection.ping()
        return True
    except Exception:
        return False
