"""Contacts CRUD. Orphan contacts (buyer_id = null) are allowed."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import ContactCreate, ContactOut, ContactUpdate
from app.auth.deps import Principal, get_db, get_principal, get_scoped_or_404
from app.db.models import Buyer, Contact

router = APIRouter(prefix="/contacts", tags=["contacts"])


def _validate_buyer(db: Session, buyer_id: str | None, principal: Principal) -> None:
    if buyer_id is None:
        return
    buyer = db.get(Buyer, buyer_id)
    if buyer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buyer not found")
    if buyer.company_id != principal.company_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-tenant access denied")


@router.get("", response_model=list[ContactOut])
def list_contacts(buyer_id: str | None = None, principal: Principal = Depends(get_principal),
                  db: Session = Depends(get_db)):
    stmt = select(Contact).where(Contact.company_id == principal.company_id)
    if buyer_id is not None:
        stmt = stmt.where(Contact.buyer_id == buyer_id)
    return list(db.scalars(stmt.order_by(Contact.name)))


@router.get("/{contact_id}", response_model=ContactOut)
def get_contact(contact_id: str, principal: Principal = Depends(get_principal),
                db: Session = Depends(get_db)):
    return get_scoped_or_404(db, Contact, contact_id, principal)


@router.post("", response_model=ContactOut, status_code=201)
def create_contact(body: ContactCreate, principal: Principal = Depends(get_principal),
                   db: Session = Depends(get_db)):
    _validate_buyer(db, body.buyer_id, principal)
    contact = Contact(company_id=principal.company_id, **body.model_dump(exclude_none=True))
    db.add(contact)
    db.commit()
    return contact


@router.patch("/{contact_id}", response_model=ContactOut)
def update_contact(contact_id: str, body: ContactUpdate,
                   principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    contact = get_scoped_or_404(db, Contact, contact_id, principal)
    data = body.model_dump(exclude_unset=True)
    if "buyer_id" in data:
        _validate_buyer(db, data["buyer_id"], principal)
    for k, v in data.items():
        setattr(contact, k, v)
    db.commit()
    return contact
