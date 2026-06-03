"""Auth dependencies + the tenant-scoping helper.

`Principal` is the (user_id, company_id) pair decoded from the JWT. Every bearer
route depends on `get_principal`, and every row lookup goes through
`get_scoped_or_404`, which enforces the 401/403/404 contract:
  - 401: token missing / expired / invalid
  - 403: authenticated, but the row belongs to a different tenant
  - 404: the row genuinely does not exist in *any* tenant
"""
from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import decode_access_token
from app.db.session import get_db

_bearer = HTTPBearer(auto_error=False)


@dataclass
class Principal:
    user_id: str
    company_id: str


def get_principal(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Principal:
    if creds is None or not creds.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        payload = decode_access_token(creds.credentials)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user_id, company_id = payload.get("user_id"), payload.get("company_id")
    if not user_id or not company_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Malformed token")
    return Principal(user_id=user_id, company_id=company_id)


def get_scoped_or_404(db: Session, model, row_id: str, principal: Principal):
    """Fetch a row by id, enforcing tenant isolation.

    Distinguishes 403 (exists in another tenant) from 404 (does not exist).
    """
    row = db.get(model, row_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} not found")
    if getattr(row, "company_id", None) != principal.company_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-tenant access denied")
    return row


__all__ = ["Principal", "get_principal", "get_scoped_or_404", "get_db", "select"]
