from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, and_, func
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.models import Business, Organization
from backend.app.models import (
    RawEvent, Account, Category, CategoryRule,
    TxnCategorization, BusinessCategoryMap,
    BusinessIntegrationProfile,
)
from backend.app.norma.categorize_brain import brain

# ✅ if you want seeding guaranteed before rules
from backend.app.services.category_seed import seed_coa_and_categories_and_mappings

router = APIRouter(prefix="/admin", tags=["admin"])


# -------------------------
# Existing endpoints
# -------------------------

@router.post("/business/{business_id}/wipe")
def wipe_business_data(business_id: str, db: Session = Depends(get_db)):
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="business not found")

    db.execute(delete(TxnCategorization).where(TxnCategorization.business_id == business_id))
    db.execute(delete(CategoryRule).where(CategoryRule.business_id == business_id))
    db.execute(delete(BusinessCategoryMap).where(BusinessCategoryMap.business_id == business_id))
    db.execute(delete(Category).where(Category.business_id == business_id))
    db.execute(delete(Account).where(Account.business_id == business_id))
    db.execute(delete(RawEvent).where(RawEvent.business_id == business_id))
    db.execute(delete(BusinessIntegrationProfile).where(BusinessIntegrationProfile.business_id == business_id))

    db.commit()
    return {"status": "ok", "wiped_business_id": business_id}


@router.delete("/business/{business_id}")
def delete_business(business_id: str, db: Session = Depends(get_db)):
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="business not found")

    db.delete(biz)
    db.commit()
    return {"status": "ok", "deleted_business_id": business_id}


@router.delete("/organization/{org_id}")
def delete_organization(org_id: str, db: Session = Depends(get_db)):
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="organization not found")

    db.delete(org)
    db.commit()
    return {"status": "ok", "deleted_org_id": org_id}


# -------------------------
# ✅ NEW: Bulk Rules (teach vendors fast)
# -------------------------

class BulkRuleIn(BaseModel):
    contains_text: str = Field(min_length=1, max_length=120)
    category_id: str
    direction: Optional[str] = None   # "inflow" | "outflow" | None
    account: Optional[str] = None     # depends on your txn.account values, else None
    priority: int = 100
    active: bool = True


class BulkRulesRequest(BaseModel):
    rules: List[BulkRuleIn]


@router.post("/business/{business_id}/rules/bulk_upsert")
def bulk_upsert_rules(business_id: str, req: BulkRulesRequest, db: Session = Depends(get_db)):
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="business not found")

    # ensure COA/categories/mappings exist
    seed_coa_and_categories_and_mappings(db, business_id)

    # validate category ids are in this business
    valid_cat_ids = set(
        db.execute(select(Category.id).where(Category.business_id == business_id)).scalars().all()
    )

    added = 0
    updated = 0
    skipped = 0

    for r in req.rules:
        needle = (r.contains_text or "").strip().lower()
        if not needle:
            skipped += 1
            continue

        if r.category_id not in valid_cat_ids:
            raise HTTPException(status_code=400, detail=f"category_id not in business: {r.category_id}")

        existing = db.execute(
            select(CategoryRule).where(
                and_(
                    CategoryRule.business_id == business_id,
                    CategoryRule.contains_text == needle,
                    CategoryRule.category_id == r.category_id,
                )
            )
        ).scalar_one_or_none()

        if existing:
            existing.direction = r.direction
            existing.account = r.account
            existing.priority = r.priority
            existing.active = r.active
            db.add(existing)
            updated += 1
        else:
            db.add(
                CategoryRule(
                    business_id=business_id,
                    category_id=r.category_id,
                    contains_text=needle,
                    direction=r.direction,
                    account=r.account,
                    priority=r.priority,
                    active=r.active,
                )
            )
            added += 1

    db.commit()
    return {"status": "ok", "added": added, "updated": updated, "skipped": skipped}


# -------------------------
# ✅ Optional convenience: bulk upsert by category NAME
# -------------------------

class BulkRuleByNameIn(BaseModel):
    contains_text: str = Field(min_length=1, max_length=120)
    category_name: str = Field(min_length=1, max_length=120)
    direction: Optional[str] = None
    account: Optional[str] = None
    priority: int = 100
    active: bool = True


class BulkRulesByNameRequest(BaseModel):
    rules: List[BulkRuleByNameIn]


@router.post("/business/{business_id}/rules/bulk_upsert_by_name")
def bulk_upsert_rules_by_name(business_id: str, req: BulkRulesByNameRequest, db: Session = Depends(get_db)):
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="business not found")

    seed_coa_and_categories_and_mappings(db, business_id)

    # map category name -> id (case-insensitive)
    cats = db.execute(select(Category).where(Category.business_id == business_id)).scalars().all()
    cat_by_name = {c.name.strip().lower(): c.id for c in cats}

    added = 0
    updated = 0
    skipped = 0

    for r in req.rules:
        needle = (r.contains_text or "").strip().lower()
        cname = (r.category_name or "").strip().lower()
        if not needle or not cname:
            skipped += 1
            continue

        cat_id = cat_by_name.get(cname)
        if not cat_id:
            raise HTTPException(status_code=400, detail=f"category_name not found in business: {r.category_name}")

        existing = db.execute(
            select(CategoryRule).where(
                and_(
                    CategoryRule.business_id == business_id,
                    CategoryRule.contains_text == needle,
                    CategoryRule.category_id == cat_id,
                )
            )
        ).scalar_one_or_none()

        if existing:
            existing.direction = r.direction
            existing.account = r.account
            existing.priority = r.priority
            existing.active = r.active
            db.add(existing)
            updated += 1
        else:
            db.add(
                CategoryRule(
                    business_id=business_id,
                    category_id=cat_id,
                    contains_text=needle,
                    direction=r.direction,
                    account=r.account,
                    priority=r.priority,
                    active=r.active,
                )
            )
            added += 1

    db.commit()
    return {"status": "ok", "added": added, "updated": updated, "skipped": skipped}
