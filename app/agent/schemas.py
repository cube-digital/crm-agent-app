"""Typed I/O for the agent: the final NextBestAction the agent must produce."""
from __future__ import annotations

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    activity_id: str = Field(description="The graph Activity id this claim rests on")
    subject: str | None = Field(default=None, description="Activity subject line")
    timestamp: str | None = Field(default=None, description="ISO timestamp of the activity")


class NextBestAction(BaseModel):
    """The agent's grounded recommendation for a single deal."""

    no_action: bool = Field(
        description="True when there is nothing worth doing now (healthy deal mid-flight "
        "with no open thread, or a closed deal). When true, leave action/evidence empty."
    )
    action: str | None = Field(
        default=None,
        description="The single most valuable next step, specific to THIS deal "
        "(who to contact, about what, referencing the concrete thread).",
    )
    rationale: str | None = Field(
        default=None, description="One sentence explaining why, grounded in the evidence."
    )
    urgency: str = Field(default="low", description="low | medium | high")
    evidence: list[Evidence] = Field(
        default_factory=list,
        description="Activities (ids + subjects + timestamps) that justify the recommendation.",
    )
