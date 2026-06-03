"""Auth routes: signup (creates + seeds a tenant), login, me."""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.proactive import run_scan_for_tenant
from app.api.schemas import (
    LoginRequest,
    MeResponse,
    SignupRequest,
    TokenResponse,
)
from app.auth.deps import Principal, get_db, get_principal
from app.auth.security import create_access_token, hash_password, verify_password
from app.db.models import Company, User
from app.graph.build import build_graph
from app.seed.seeder import seed_tenant

log = logging.getLogger("crm.auth")
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse)
def signup(body: SignupRequest, background: BackgroundTasks,
           db: Session = Depends(get_db)) -> TokenResponse:
    existing = db.scalar(select(User).where(User.email == body.email))
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    company = Company(name=body.company_name or body.email.split("@")[0] + "'s CRM")
    db.add(company)
    db.flush()  # assign company.id

    user = User(
        company_id=company.id,
        email=body.email,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.flush()

    # Seed the full sample dataset into this fresh tenant, then build its graph.
    log.info("Seeding tenant %s from fixtures", company.id)
    seed_tenant(db, company.id)
    db.commit()

    log.info("Building knowledge graph for tenant %s", company.id)
    try:
        build_graph(company.id)
    except Exception:  # graph is best-effort at signup; /graph/rebuild can retry
        log.exception("Graph build failed for tenant %s (continuing)", company.id)

    # Kick off the first proactive scan in the background so the inbox is
    # populated within ~30s of landing (the demo path), without blocking signup.
    background.add_task(run_scan_for_tenant, company.id)

    token = create_access_token(user.id, company.id)
    return TokenResponse(access_token=token, company_id=company.id, user_id=user.id)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == body.email))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    token = create_access_token(user.id, user.company_id)
    return TokenResponse(access_token=token, company_id=user.company_id, user_id=user.id)


@router.get("/me", response_model=MeResponse)
def me(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> MeResponse:
    user = db.get(User, principal.user_id)
    company = db.get(Company, principal.company_id)
    if user is None or company is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown principal")
    return MeResponse(
        user_id=user.id,
        email=user.email,
        company_id=company.id,
        company_name=company.name,
        proactive_enabled=company.proactive_enabled,
    )
