from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.coa_templates import DEFAULT_COA
from backend.app.db import get_db
from backend.app.models import Account, Business, Organization, RawEvent
from backend.app.norma.merchant import merchant_key
from backend.app.services import categorize_service
from backend.app.models import BusinessIntegrationProfile

router = APIRouter()


# ----------------------------
# Request/Response Schemas
# ----------------------------

class OrgCreate(BaseModel):
    name: str


class BusinessCreate(BaseModel):
    org_id: str
    name: str
    industry: Optional[str] = None


class ApplyTemplateRequest(BaseModel):
    template_name: str = "default"  # currently unused (kept for future)
    overwrite: bool = False


class RawEventIn(BaseModel):
    business_id: str
    source: str
    source_event_id: str
    occurred_at: datetime
    payload: dict


class LabelRequest(BaseModel):
    description: str
    business_id: str
    canonical_name: str
    category: str
    confidence: float = 0.92


# NOTE: These are only needed if you’re returning transactions from THIS router.
# If transactions live under /demo, move these to demo schemas instead.
class NormalizedTxnOut(BaseModel):
    id: str
    source_event_id: str
    occurred_at: datetime
    date: date
    description: str
    amount: float
    direction: Literal["inflow", "outflow"]
    account: str
    category: str
    counterparty_hint: Optional[str] = None


class TransactionsResponse(BaseModel):
    business_id: str
    as_of: datetime
    last_event_occurred_at: Optional[datetime] = None
    count: int
    transactions: list[NormalizedTxnOut]


# ----------------------------
# Health
# ----------------------------

@router.get("/health")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


# ----------------------------
# Orgs / Businesses
# ----------------------------

@router.post("/orgs")
def create_org(req: OrgCreate, db: Session = Depends(get_db)):
    org = Organization(name=req.name)
    db.add(org)
    db.commit()
    db.refresh(org)
    return {"org_id": org.id, "name": org.name}


@router.post("/businesses")
def create_business(req: BusinessCreate, db: Session = Depends(get_db)):
    org = db.get(Organization, req.org_id)
    if not org:
        raise HTTPException(404, "org_id not found")

    biz = Business(org_id=req.org_id, name=req.name, industry=req.industry)
    db.add(biz)
    db.flush()  # ensures biz.id exists

# seed COA
    for a in DEFAULT_COA:
        db.add(Account(business_id=biz.id, **a))

    db.add(BusinessIntegrationProfile(business_id=biz.id))
    db.commit()
    db.refresh(biz)



    return {"business_id": biz.id, "name": biz.name, "org_id": biz.org_id}


# ----------------------------
# Chart of Accounts
# ----------------------------

@router.post("/businesses/{business_id}/accounts/apply_template")
def apply_coa_template(business_id: str, req: ApplyTemplateRequest, db: Session = Depends(get_db)):
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(404, "business not found")

    if req.overwrite:
        db.query(Account).filter(Account.business_id == business_id).delete()

    existing = db.execute(
        select(Account.code, Account.name).where(Account.business_id == business_id)
    ).all()
    existing_set = {(c, n) for (c, n) in existing}

    created = 0
    for a in DEFAULT_COA:
        key = (a.get("code"), a["name"])
        if key in existing_set:
            continue
        db.add(Account(business_id=business_id, **a))
        created += 1

    db.commit()
    return {"status": "ok", "created": created}


@router.get("/businesses/{business_id}/accounts")
def list_accounts(business_id: str, db: Session = Depends(get_db)):
    rows = db.execute(
        select(Account)
        .where(Account.business_id == business_id, Account.active == True)  # noqa: E712
        .order_by(Account.code)
    ).scalars().all()

    return {
        "business_id": business_id,
        "accounts": [
            {
                "id": r.id,
                "code": r.code,
                "name": r.name,
                "type": r.type,
                "subtype": r.subtype,
                "active": r.active,
            }
            for r in rows
        ],
    }


# ----------------------------
# Raw Events Ingest
# ----------------------------

@router.post("/raw_events")
def ingest_raw_event(req: RawEventIn, db: Session = Depends(get_db)):
    exists = db.execute(
        select(RawEvent.id).where(
            RawEvent.business_id == req.business_id,
            RawEvent.source == req.source,
            RawEvent.source_event_id == req.source_event_id,
        )
    ).first()

    if exists:
        return {"status": "duplicate"}

    ev = RawEvent(
        business_id=req.business_id,
        source=req.source,
        source_event_id=req.source_event_id,
        occurred_at=req.occurred_at,
        payload=req.payload,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return {"status": "ok", "raw_event_id": ev.id}


# ----------------------------
# Brain Labeling
# ----------------------------

@router.post("/brain/label")
def brain_label(req: LabelRequest, db: Session = Depends(get_db)):
    return categorize_service.legacy_brain_label(db, req)
