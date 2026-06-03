"""SQLAlchemy ORM models.

Design notes:
- Every tenant-owned table carries an indexed ``company_id`` — this is the spine
  of multi-tenant isolation. Queries always filter on it.
- ``Company`` is the tenant (created at signup). The fixtures' own "company"
  record (Narrio) is *seed data*: on signup we copy all fixture entities under
  the new tenant's ``company_id`` with fresh UUIDs.
- ``Recommendation`` is the proactive "inbox": rows written by the agent triggers
  and read back by ``GET /proactive/feed``.
- IDs are stored as 36-char UUID strings (the fixtures use UUID strings; keeping
  the type identical avoids casting headaches and keeps the graph keys readable).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# --------------------------------------------------------------------------- #
# Tenant + auth
# --------------------------------------------------------------------------- #
class Company(Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    proactive_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# --------------------------------------------------------------------------- #
# CRM entities (seeded from fixtures.json, then CRUD-managed)
# --------------------------------------------------------------------------- #
class Pipeline(Base):
    __tablename__ = "pipelines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), index=True)
    label: Mapped[str] = mapped_column(String(255))
    object_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    display_order: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PipelineStage(Base):
    __tablename__ = "pipeline_stages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), index=True)
    pipeline_id: Mapped[str] = mapped_column(String(36), index=True)
    label: Mapped[str] = mapped_column(String(255))
    display_order: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Buyer(Base):
    __tablename__ = "buyers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), index=True)
    buyer_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)  # orphans allowed
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    position: Mapped[str | None] = mapped_column(String(255), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), index=True)
    pipeline_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    pipeline_stage_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    buyer_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    deal_name: Mapped[str] = mapped_column(String(512))
    stage_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    deal_amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    deal_owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    close_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_closed_won: Mapped[bool] = mapped_column(Boolean, default=False)
    source_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class DealContact(Base):
    __tablename__ = "deal_contacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), index=True)
    deal_id: Mapped[str] = mapped_column(String(36), index=True)
    contact_id: Mapped[str] = mapped_column(String(36), index=True)
    role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), index=True)
    activity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    direction: Mapped[str | None] = mapped_column(String(32), nullable=True)  # inbound/outbound/null
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ActivityLink(Base):
    __tablename__ = "activity_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), index=True)
    activity_id: Mapped[str] = mapped_column(String(36), index=True)
    entity_type: Mapped[str] = mapped_column(String(32))  # deal / buyer / contact
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    confidence: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


Index("ix_activity_links_entity", ActivityLink.entity_type, ActivityLink.entity_id)


# --------------------------------------------------------------------------- #
# Proactive inbox
# --------------------------------------------------------------------------- #
class DealEnrichment(Base):
    """LLM-derived attributes for a deal, cached in Postgres.

    Generated once (Haiku) at seed time, then *copied* onto the Deal graph node by
    the graph build. This keeps `/graph/rebuild` LLM-free + deterministic, and
    embodies the DB split: Postgres is the attribute store (raw + derived), the
    graph is the reasoning/traversal surface the agent queries.
    """
    __tablename__ = "deal_enrichment"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), index=True)
    deal_id: Mapped[str] = mapped_column(String(36), index=True, unique=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    sentiment: Mapped[str | None] = mapped_column(String(32), nullable=True)
    key_topics: Mapped[list | None] = mapped_column(JSON, nullable=True)
    open_asks: Mapped[list | None] = mapped_column(JSON, nullable=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), index=True)
    deal_id: Mapped[str] = mapped_column(String(36), index=True)
    deal_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    nba: Mapped[str | None] = mapped_column(Text, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON list of {activity_id, subject, timestamp}
    evidence: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    score: Mapped[float] = mapped_column(default=0.0)
    urgency: Mapped[str | None] = mapped_column(String(32), nullable=True)
    no_action: Mapped[bool] = mapped_column(Boolean, default=False)
    trigger_source: Mapped[str | None] = mapped_column(String(32), nullable=True)  # scheduled / reactive / manual
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
