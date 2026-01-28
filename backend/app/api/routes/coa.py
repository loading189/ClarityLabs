# backend/app/api/coa.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, List, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.models import Business, Account
import uuid

router = APIRouter(prefix="/coa", tags=["coa"])

AccountType = Literal["asset", "liability", "equity", "revenue", "expense"]

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def uuid_str() -> str:
    return str(uuid.uuid4())

def _require_business(db: Session, business_id: str) -> Business:
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="business not found")
    return biz

# -------------------------
# Schemas
# -------------------------

class AccountOut(BaseModel):
    id: str
    business_id: str
    code: Optional[str] = None
    name: str
    type: AccountType
    subtype: Optional[str] = None
    active: bool
    created_at: datetime

class AccountCreateIn(BaseModel):
    code: Optional[str] = Field(default=None, max_length=30)
    name: str = Field(min_length=1, max_length=200)
    type: AccountType
    subtype: Optional[str] = Field(default=None, max_length=80)
    active: bool = True

class AccountUpdateIn(BaseModel):
    code: Optional[str] = Field(default=None, max_length=30)
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    type: Optional[AccountType] = None
    subtype: Optional[str] = Field(default=None, max_length=80)
    active: Optional[bool] = None

# -------------------------
# Endpoints
# -------------------------

@router.get("/business/{business_id}/accounts", response_model=List[AccountOut])
def list_accounts(
    business_id: str,
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
):
    _require_business(db, business_id)

    q = select(Account).where(Account.business_id == business_id)
    if not include_inactive:
        q = q.where(Account.active == True)  # noqa: E712
    q = q.order_by(Account.code.asc().nulls_last(), Account.name.asc())

    rows = db.execute(q).scalars().all()
    return rows

@router.post("/business/{business_id}/accounts", response_model=AccountOut)
def create_account(business_id: str, req: AccountCreateIn, db: Session = Depends(get_db)):
    _require_business(db, business_id)

    # prevent duplicate codes if provided
    if req.code:
        existing = db.execute(
            select(Account.id).where(Account.business_id == business_id, Account.code == req.code)
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail="account code already exists")

    a = Account(
        id=uuid_str(),
        business_id=business_id,
        code=req.code,
        name=req.name,
        type=req.type,
        subtype=req.subtype,
        active=req.active,
        created_at=utcnow(),
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a

@router.put("/business/{business_id}/accounts/{account_id}", response_model=AccountOut)
def update_account(business_id: str, account_id: str, req: AccountUpdateIn, db: Session = Depends(get_db)):
    _require_business(db, business_id)

    a = db.get(Account, account_id)
    if not a or a.business_id != business_id:
        raise HTTPException(status_code=404, detail="account not found")

    data = req.model_dump(exclude_unset=True)

    # code uniqueness
    if "code" in data and data["code"]:
        existing = db.execute(
            select(Account.id).where(
                Account.business_id == business_id,
                Account.code == data["code"],
                Account.id != account_id,
            )
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail="account code already exists")

    for k, v in data.items():
        setattr(a, k, v)

    db.add(a)
    db.commit()
    db.refresh(a)
    return a

@router.delete("/business/{business_id}/accounts/{account_id}")
def deactivate_account(business_id: str, account_id: str, db: Session = Depends(get_db)):
    _require_business(db, business_id)

    a = db.get(Account, account_id)
    if not a or a.business_id != business_id:
        raise HTTPException(status_code=404, detail="account not found")

    a.active = False
    db.add(a)
    db.commit()
    return {"status": "ok", "account_id": account_id, "active": False}
