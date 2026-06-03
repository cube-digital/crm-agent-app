"""The next-best-action agent: a LangGraph ReAct loop over graph-backed tools.

`run_recommendation(company_id, deal_id)` returns a typed `NextBestAction`. The
loop is decoupled from the tools (app/agent/tools.py) and the prompts
(app/agent/prompts.py), so any piece can be swapped independently.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import create_react_agent

from app.agent.prompts import EXTRACTION_PROMPT, SYSTEM_PROMPT
from app.agent.schemas import NextBestAction
from app.agent.tools import make_tools
from app.config import get_settings
from app.graph import queries

log = logging.getLogger("crm.agent")


@lru_cache
def get_model(model_name: str | None = None) -> ChatAnthropic:
    s = get_settings()
    if not s.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set; the agent cannot run.")
    return ChatAnthropic(
        model=model_name or s.agent_model,
        api_key=s.anthropic_api_key,
        temperature=0,
        max_tokens=1024,
    )


def run_recommendation(company_id: str, deal_id: str,
                        model_name: str | None = None) -> NextBestAction:
    """Produce a grounded NBA for one deal, scoped to the tenant's graph."""
    overview = queries.deal_overview(company_id, deal_id)

    # The deal isn't in the graph (e.g. created after the last snapshot).
    if overview is None:
        return NextBestAction(
            no_action=True,
            rationale="Deal not present in the graph snapshot — rebuild the graph to analyze it.",
        )

    # Closed deals: stay silent, no LLM spend.
    if overview.get("is_closed"):
        log.info("Deal %s is closed; returning no_action without LLM call", deal_id)
        return NextBestAction(
            no_action=True,
            rationale=f"Deal is closed ({overview.get('stage_label')}); nothing to do.",
        )

    model = get_model(model_name)
    tools = make_tools(company_id, deal_id)
    agent = create_react_agent(model, tools, state_modifier=SYSTEM_PROMPT)

    user_msg = (
        f"Analyze deal id '{deal_id}' (name: {overview.get('deal_name')!r}, "
        f"stage: {overview.get('stage_label')!r}) and recommend the next best action."
    )
    log.info("Running agent for deal %s", deal_id)
    state = agent.invoke(
        {"messages": [("user", user_msg)]},
        config={"recursion_limit": 12},
    )
    messages = state["messages"]

    # Convert the agent's free-text conclusion into the typed output. The full
    # transcript (incl. tool results with real activity ids) is in scope so the
    # evidence ids are grounded.
    extractor = model.with_structured_output(NextBestAction)
    nba: NextBestAction = extractor.invoke(messages + [("user", EXTRACTION_PROMPT)])
    log.info(
        "Agent NBA for deal %s: no_action=%s urgency=%s evidence=%d",
        deal_id, nba.no_action, nba.urgency, len(nba.evidence),
    )
    return nba
