"""Graph-backed agent tools.

Each tool is a thin, typed wrapper over `app.graph.queries`. They read the
**graph only** — this module deliberately does not import the Postgres layer, so
the agent can never bypass the graph back to raw SQL.

Tools are built per request with `company_id` (from the JWT) and `deal_id` bound
in via a closure, so the LLM cannot pass a different tenant's id or wander to
another deal — scoping is not left to the model.
"""
from __future__ import annotations

import json
import logging

from langchain_core.tools import StructuredTool

from app.graph import queries

log = logging.getLogger("crm.agent.tools")


def _json(obj) -> str:
    return json.dumps(obj, default=str, ensure_ascii=False)


def make_tools(company_id: str, deal_id: str) -> list[StructuredTool]:
    """Return the graph-backed tools, scoped to one tenant + one deal."""

    def _log(name: str, result) -> str:
        out = _json(result)
        log.info("tool %s(deal=%s) -> %s", name, deal_id, out[:500])
        return out

    def get_deal_overview() -> str:
        """Snapshot of the deal: stage, buyer, owner, activity counts (inbound/
        outbound), first/last activity, days since last activity, contact count."""
        return _log("get_deal_overview", queries.deal_overview(company_id, deal_id))

    def get_recent_activities(limit: int = 10) -> str:
        """The most recent activities on the deal timeline (newest first), with
        id, type, subject, direction and a text snippet. Use to read the thread."""
        return _log("get_recent_activities", queries.recent_activities(company_id, deal_id, limit))

    def find_silent_period() -> str:
        """Days since last activity, last inbound (buyer→us) and last outbound
        (us→buyer). The core signal for detecting a stalled/silent deal."""
        return _log("find_silent_period", queries.silent_period(company_id, deal_id))

    def get_stakeholder_map() -> str:
        """Contacts involved in the deal with their role/confidence. Note: roles
        are mostly 'unknown' in this dataset, so weigh this signal lightly."""
        return _log("get_stakeholder_map", queries.stakeholder_map(company_id, deal_id))

    def get_stage_context() -> str:
        """Current funnel stage, its order index, the next stage, and whether the
        deal is in a terminal (Closed Won/Lost) stage."""
        return _log("get_stage_context", queries.stage_context(company_id, deal_id))

    specs = [
        (get_deal_overview, "get_deal_overview"),
        (get_recent_activities, "get_recent_activities"),
        (find_silent_period, "find_silent_period"),
        (get_stakeholder_map, "get_stakeholder_map"),
        (get_stage_context, "get_stage_context"),
    ]
    return [
        StructuredTool.from_function(func=fn, name=name, description=fn.__doc__)
        for fn, name in specs
    ]
