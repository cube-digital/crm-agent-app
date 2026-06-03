"""Graph schema constants — node labels, edge types, and the canonical funnel.

The graph is deliberately *not* a 1:1 mirror of the SQL tables. We model the
entities a sales rep reasons about (Deal, Buyer, Contact, Stage, Activity) and
connect them with typed, directional edges that match the agent's traversals.
See SCHEMA.md for the full rationale + diagram.
"""
from __future__ import annotations

# Node labels
DEAL = "Deal"
BUYER = "Buyer"
CONTACT = "Contact"
STAGE = "Stage"
ACTIVITY = "Activity"

# Edge types
WITH_BUYER = "WITH_BUYER"      # (Deal)-[:WITH_BUYER]->(Buyer)
WORKS_AT = "WORKS_AT"          # (Contact)-[:WORKS_AT]->(Buyer)
INVOLVED_IN = "INVOLVED_IN"    # (Contact)-[:INVOLVED_IN {role}]->(Deal)
IN_STAGE = "IN_STAGE"          # (Deal)-[:IN_STAGE]->(Stage)
NEXT = "NEXT"                  # (Stage)-[:NEXT]->(Stage)  funnel progression
ON_DEAL = "ON_DEAL"            # (Activity)-[:ON_DEAL {direction,timestamp}]->(Deal)

# Canonical funnel order, derived from the fixtures' display_order 0..8 rows.
# `Long Term Nurture` is a side/holding state, not a forward step.
CANONICAL_STAGE_ORDER = [
    "Appointment Scheduled",
    "Qualified To Buy",
    "Presentation Scheduled",
    "Decision Maker Bought-In",
    "POC",
    "Contract Sent",
    "Closed Won",
    "Closed Lost",
    "Long Term Nurture",
]

# Stages that mean the deal is finished — agent stays silent on these.
TERMINAL_STAGES = {"Closed Won", "Closed Lost"}

# The linear part of the funnel used for NEXT edges (terminals/side-states excluded).
FUNNEL_PATH = [
    "Appointment Scheduled",
    "Qualified To Buy",
    "Presentation Scheduled",
    "Decision Maker Bought-In",
    "POC",
    "Contract Sent",
]


def stage_index(label: str | None) -> int:
    """Funnel position of a stage label (-1 if unknown)."""
    if label is None:
        return -1
    try:
        return CANONICAL_STAGE_ORDER.index(label)
    except ValueError:
        return -1
