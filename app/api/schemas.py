"""Pydantic request/response models for the HTTP API.

Response models use `from_attributes` so we can return ORM objects directly.
Read models are deliberately permissive about nulls — the seed data is messy.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

ORM = ConfigDict(from_attributes=True)


# --- Auth ---
class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    company_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    company_id: str
    user_id: str


class MeResponse(BaseModel):
    user_id: str
    email: str
    company_id: str
    company_name: str
    proactive_enabled: bool


# --- Pipelines / stages ---
class PipelineOut(BaseModel):
    model_config = ORM
    id: str
    label: str
    object_type: str | None = None
    display_order: int
    is_active: bool


class StageOut(BaseModel):
    model_config = ORM
    id: str
    pipeline_id: str
    label: str
    display_order: int


# --- Buyers ---
class BuyerCreate(BaseModel):
    name: str
    description: str | None = None
    website_url: str | None = None
    linkedin_url: str | None = None
    industry: str | None = None


class BuyerUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    website_url: str | None = None
    linkedin_url: str | None = None
    industry: str | None = None


class BuyerOut(BaseModel):
    model_config = ORM
    id: str
    name: str
    description: str | None = None
    website_url: str | None = None
    linkedin_url: str | None = None
    industry: str | None = None


# --- Contacts ---
class ContactCreate(BaseModel):
    name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    position: str | None = None
    buyer_id: str | None = None


class ContactUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    position: str | None = None
    buyer_id: str | None = None


class ContactOut(BaseModel):
    model_config = ORM
    id: str
    buyer_id: str | None = None
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    position: str | None = None


# --- Deals ---
class DealCreate(BaseModel):
    deal_name: str
    buyer_id: str | None = None
    pipeline_id: str | None = None
    pipeline_stage_id: str | None = None
    deal_owner: str | None = None
    deal_amount: Decimal | None = None
    currency: str | None = None
    close_date: datetime | None = None


class DealUpdate(BaseModel):
    pipeline_stage_id: str | None = None
    deal_owner: str | None = None
    deal_amount: Decimal | None = None
    close_date: datetime | None = None
    is_closed: bool | None = None
    is_closed_won: bool | None = None


class DealOut(BaseModel):
    model_config = ORM
    id: str
    deal_name: str
    buyer_id: str | None = None
    pipeline_id: str | None = None
    pipeline_stage_id: str | None = None
    stage_label: str | None = None
    deal_amount: Decimal | None = None
    currency: str | None = None
    deal_owner: str | None = None
    close_date: datetime | None = None
    is_closed: bool
    is_closed_won: bool
    last_activity_at: datetime | None = None


# --- Activities ---
class ActivityCreate(BaseModel):
    activity_type: str
    subject: str | None = None
    full_text: str | None = None
    direction: str | None = None
    timestamp: datetime | None = None


class ActivityOut(BaseModel):
    model_config = ORM
    id: str
    activity_type: str | None = None
    subject: str | None = None
    full_text: str | None = None
    direction: str | None = None
    source: str | None = None
    timestamp: datetime | None = None


class Page(BaseModel):
    """Wrapper for paginated lists."""
    items: list
    total: int
    limit: int
    offset: int


# --- Deal contacts ---
class DealContactCreate(BaseModel):
    contact_id: str
    role: str | None = "unknown"


class DealContactRoleUpdate(BaseModel):
    role: str


class DealContactOut(BaseModel):
    model_config = ORM
    id: str
    deal_id: str
    contact_id: str
    role: str | None = None
    confidence: str | None = None


# --- Agent / recommendations ---
class EvidenceItem(BaseModel):
    activity_id: str
    subject: str | None = None
    timestamp: str | None = None


class RecommendationOut(BaseModel):
    deal_id: str
    deal_name: str | None = None
    no_action: bool
    nba: str | None = None
    rationale: str | None = None
    urgency: str | None = None
    score: float = 0.0
    evidence: list[EvidenceItem] = []
    trigger_source: str | None = None
    created_at: datetime | None = None
