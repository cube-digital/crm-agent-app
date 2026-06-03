"""Conversational follow-up agent for a single deal.

Same graph-backed tools as the recommendation agent, but it answers the rep's
follow-up questions in a chat thread instead of producing a one-shot NBA. Reads
the graph only.
"""
from __future__ import annotations

import logging

from langgraph.prebuilt import create_react_agent

from app.agent.graph_agent import get_model
from app.agent.prompts import CHAT_SYSTEM_PROMPT
from app.agent.tools import make_tools
from app.graph import queries

log = logging.getLogger("crm.agent.chat")

_ROLE = {"user": "human", "assistant": "ai", "human": "human", "ai": "ai"}


def _text(content) -> str:
    """Anthropic content may be a string or a list of blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in content
        ).strip()
    return str(content)


def run_chat(company_id: str, deal_id: str, history: list[dict]) -> str:
    """Answer the latest follow-up, given prior conversation, scoped to one deal."""
    if queries.deal_overview(company_id, deal_id) is None:
        return "I don't have this deal in the graph snapshot yet — try rebuilding the graph."

    messages = [
        (_ROLE.get(m.get("role", "user"), "human"), m["content"])
        for m in history
        if m.get("content")
    ]
    if not messages:
        return "Ask me anything about this deal."

    agent = create_react_agent(get_model(), make_tools(company_id, deal_id),
                               state_modifier=CHAT_SYSTEM_PROMPT)
    log.info("Chat turn for deal %s (%d prior messages)", deal_id, len(messages))
    state = agent.invoke({"messages": messages}, config={"recursion_limit": 12})
    return _text(state["messages"][-1].content)
