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


# Human/agent-readable schema, returned by the get_graph_schema tool so the agent
# can author its own Cypher. Kept in sync with build.py node/edge construction.
SCHEMA_DESCRIPTION = """\
KNOWLEDGE GRAPH SCHEMA (FalkorDB, Cypher). You are querying ONE tenant's graph;
every node below belongs to this tenant — there is no company_id to filter on.

NODES
  (:Deal {id, name, stage_label, is_closed, is_closed_won, owner,
          activity_count, inbound_count, outbound_count,
          first_activity_at, last_activity_at,           // ISO 8601 strings
          summary, sentiment, key_topics, open_asks})    // LLM-derived attributes
  (:Buyer {id, name, industry})
  (:Contact {id, name, email, position, buyer_id})
  (:Stage {label, order_index})                          // order_index = funnel position
  (:Activity {id, type, subject, direction, timestamp, ts, snippet})
        // direction in 'inbound'|'outbound'|'unknown'; timestamp = ISO string;
        // ts = epoch seconds (use for ORDER BY / recency); snippet = text excerpt

EDGES (all directional)
  (:Deal)-[:WITH_BUYER]->(:Buyer)
  (:Contact)-[:WORKS_AT]->(:Buyer)
  (:Contact)-[:INVOLVED_IN {role, confidence}]->(:Deal)   // role often 'unknown'
  (:Deal)-[:IN_STAGE]->(:Stage)
  (:Stage)-[:NEXT]->(:Stage)                              // funnel progression
  (:Activity)-[:ON_DEAL {direction, ts}]->(:Deal)

NOTES
  - sentiment/summary/key_topics/open_asks are the enriched attributes — prefer
    them for a fast read of the deal's state, then drill into Activity nodes.
  - "Days since X" is not stored (the snapshot is static): fetch the relevant
    timestamp and compute against the current date in your reasoning.
  - deal_amount is always 0 and contact role is mostly 'unknown' in this data.

EXAMPLE QUERIES
  // Deal overview incl. enrichment
  MATCH (d:Deal {id:$id}) OPTIONAL MATCH (d)-[:WITH_BUYER]->(b:Buyer)
  RETURN d.name, d.stage_label, d.is_closed, d.summary, d.sentiment,
         d.open_asks, d.last_activity_at, b.name
  // Last inbound from the buyer (silence detection)
  MATCH (a:Activity)-[:ON_DEAL]->(:Deal {id:$id}) WHERE a.direction='inbound'
  RETURN a.subject, a.timestamp ORDER BY a.ts DESC LIMIT 1
  // Recent thread
  MATCH (a:Activity)-[:ON_DEAL]->(:Deal {id:$id})
  RETURN a.id, a.direction, a.subject, a.timestamp, a.snippet ORDER BY a.ts DESC LIMIT 8
  // Stakeholders
  MATCH (c:Contact)-[r:INVOLVED_IN]->(:Deal {id:$id})
  RETURN c.name, c.email, c.position, r.role
"""


def stage_index(label: str | None) -> int:
    """Funnel position of a stage label (-1 if unknown)."""
    if label is None:
        return -1
    try:
        return CANONICAL_STAGE_ORDER.index(label)
    except ValueError:
        return -1
