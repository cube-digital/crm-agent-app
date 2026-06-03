"""Buyers (accounts) CRUD."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import BuyerCreate, BuyerOut, BuyerUpdate
from app.auth.deps import Principal, get_db, get_principal, get_scoped_or_404
from app.db.models import Buyer

router = APIRouter(prefix="/buyers", tags=["buyers"])


@router.get("", response_model=list[BuyerOut])
def list_buyers(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    return list(db.scalars(
        select(Buyer).where(Buyer.company_id == principal.company_id).order_by(Buyer.name)
    ))


@router.get("/{buyer_id}", response_model=BuyerOut)
def get_buyer(buyer_id: str, principal: Principal = Depends(get_principal),
              db: Session = Depends(get_db)):
    return get_scoped_or_404(db, Buyer, buyer_id, principal)


@router.post("", response_model=BuyerOut, status_code=201)
def create_buyer(body: BuyerCreate, principal: Principal = Depends(get_principal),
                 db: Session = Depends(get_db)):
    buyer = Buyer(company_id=principal.company_id, **body.model_dump(exclude_none=True))
    db.add(buyer)
    db.commit()
    return buyer


@router.patch("/{buyer_id}", response_model=BuyerOut)
def update_buyer(buyer_id: str, body: BuyerUpdate, principal: Principal = Depends(get_principal),
                 db: Session = Depends(get_db)):
    buyer = get_scoped_or_404(db, Buyer, buyer_id, principal)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(buyer, k, v)
    db.commit()
    return buyer
