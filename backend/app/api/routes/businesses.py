from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.coa_templates import DEFAULT_COA
from backend.app.db import get_db
from backend.app.models import Account, Business, BusinessIntegrationProfile, Organization
from backend.app.services import business_service

router = APIRouter(prefix="/api/businesses", tags=["businesses"])


class BusinessCreateIn(BaseModel):
    name: str
    is_demo: bool = False


@router.post("")
def create_business(payload: BusinessCreateIn, db: Session = Depends(get_db)):
    org = db.execute(select(Organization).order_by(Organization.created_at.asc())).scalars().first()
    if not org:
        org = Organization(name="Default Organization")
        db.add(org)
        db.flush()

    biz = Business(
        org_id=org.id,
        name=payload.name.strip() or "New Business",
        created_at=datetime.now(timezone.utc),
    )
    db.add(biz)
    db.flush()

    for a in DEFAULT_COA:
        db.add(Account(business_id=biz.id, **a))
    db.add(BusinessIntegrationProfile(business_id=biz.id))
    db.commit()
    db.refresh(biz)

    return {
        "id": biz.id,
        "name": biz.name,
        "org_id": biz.org_id,
        "created_at": biz.created_at,
        "is_demo": payload.is_demo,
    }


@router.delete("/{business_id}")
def delete_business(
    business_id: str,
    confirm: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    if not confirm:
        raise HTTPException(status_code=400, detail="confirm=true is required")
    deleted = business_service.hard_delete_business(db, business_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="business not found")
    return {"deleted": True, "business_id": business_id}
