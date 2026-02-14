from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.params import Query as QueryParam
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.api.deps import require_membership_dep
from backend.app.db import get_db
from backend.app.services import categorize_service

router = APIRouter(
    prefix="/categorize",
    tags=["categorize"],
    dependencies=[Depends(require_membership_dep())],
)


class NormalizedTxnOut(BaseModel):
    source_event_id: str
    occurred_at: datetime
    description: str
    amount: float
    direction: str
    account: str
    category_hint: str

    suggested_system_key: Optional[str] = None
    suggestion_source: Optional[str] = None
    confidence: Optional[float] = None
    reason: Optional[str] = None

    suggested_category_id: Optional[str] = None
    suggested_category_name: Optional[str] = None

    merchant_key: Optional[str] = None




class TxnsToCategorizePageOut(BaseModel):
    items: List[NormalizedTxnOut]
    total_count: int
    has_more: bool
    next_offset: Optional[int] = None

class LabelVendorIn(BaseModel):
    source_event_id: str
    system_key: str
    canonical_name: Optional[str] = None
    confidence: float = 0.92


class BrainVendorOut(BaseModel):
    merchant_id: str
    canonical_name: str
    system_key: str
    confidence: float
    evidence_count: int
    updated_at: str
    alias_keys: Optional[List[str]] = None
    merchant_key: Optional[str] = None


class BrainVendorSetIn(BaseModel):
    merchant_key: str
    category_id: str
    canonical_name: Optional[str] = None


class BrainVendorForgetIn(BaseModel):
    merchant_key: str


class CategoryOut(BaseModel):
    id: str
    name: str
    system_key: Optional[str] = None
    account_id: str
    account_code: Optional[str] = None
    account_name: str


class CategorizationUpsertIn(BaseModel):
    source_event_id: str
    category_id: str
    source: str = "manual"
    confidence: float = 1.0
    note: Optional[str] = None


class BulkCategorizationIn(BaseModel):
    merchant_key: str
    category_id: str
    source: str = "bulk"
    confidence: float = 1.0
    note: Optional[str] = None


class CategorizationMetricsOut(BaseModel):
    total_events: int
    posted: int
    uncategorized: int
    suggestion_coverage: int
    brain_coverage: int


class CategoryRuleIn(BaseModel):
    contains_text: str = Field(min_length=1, max_length=120)
    category_id: str
    priority: Optional[int] = 100
    direction: Optional[str] = None
    account: Optional[str] = None
    active: Optional[bool] = True


class CategoryRuleOut(BaseModel):
    id: str
    business_id: str
    category_id: str
    contains_text: str
    direction: Optional[str] = None
    account: Optional[str] = None
    priority: int
    active: bool
    created_at: datetime
    last_run_at: Optional[datetime] = None
    last_run_updated_count: Optional[int] = None


class CategoryRulePatch(BaseModel):
    category_id: Optional[str] = None
    priority: Optional[int] = None
    active: Optional[bool] = None
    contains_text: Optional[str] = None
    direction: Optional[str] = None
    account: Optional[str] = None


class CategoryRulePreviewSample(BaseModel):
    source_event_id: str
    occurred_at: datetime
    description: str
    amount: float
    direction: str
    account: str


class CategoryRulePreviewOut(BaseModel):
    rule_id: str
    matched: int
    samples: List[CategoryRulePreviewSample]


class CategoryRuleApplyOut(BaseModel):
    rule_id: str
    matched: int
    updated: int
    audit_id: Optional[str] = None


@router.post("/business/{business_id}/label_vendor")
def label_vendor(business_id: str, req: LabelVendorIn, db: Session = Depends(get_db)):
    return categorize_service.label_vendor(db, business_id, req)


@router.get("/business/{business_id}/brain/vendors", response_model=List[BrainVendorOut])
def list_brain_vendors(business_id: str, db: Session = Depends(get_db)):
    return [BrainVendorOut(**item) for item in categorize_service.list_brain_vendors(db, business_id)]


@router.get("/business/{business_id}/brain/vendor", response_model=BrainVendorOut)
def get_brain_vendor(
    business_id: str,
    merchant_key_value: str = Query(..., alias="merchant_key"),
    db: Session = Depends(get_db),
):
    return BrainVendorOut(**categorize_service.get_brain_vendor(db, business_id, merchant_key_value))


@router.post("/business/{business_id}/brain/vendor/set", response_model=BrainVendorOut)
def set_brain_vendor(business_id: str, req: BrainVendorSetIn, db: Session = Depends(get_db)):
    return BrainVendorOut(**categorize_service.set_brain_vendor(db, business_id, req))


@router.post("/business/{business_id}/brain/vendor/forget")
def forget_brain_vendor(business_id: str, req: BrainVendorForgetIn, db: Session = Depends(get_db)):
    return categorize_service.forget_brain_vendor(db, business_id, req)


@router.get("/business/{business_id}/txns", response_model=TxnsToCategorizePageOut)
def list_txns_to_categorize(
    business_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    only_uncategorized: bool = True,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    if isinstance(start_date, QueryParam):
        start_date = None
    if isinstance(end_date, QueryParam):
        end_date = None
    payload = categorize_service.list_txns_to_categorize_page(
        db,
        business_id,
        limit=limit,
        offset=offset,
        only_uncategorized=only_uncategorized,
        start_date=start_date,
        end_date=end_date,
    )
    return {
        "items": [NormalizedTxnOut(**item) for item in payload["items"]],
        "total_count": payload["total_count"],
        "has_more": payload["has_more"],
        "next_offset": payload["next_offset"],
    }


@router.get("/business/{business_id}/categories", response_model=List[CategoryOut])
def list_categories(business_id: str, db: Session = Depends(get_db)):
    return [CategoryOut(**item) for item in categorize_service.list_categories(db, business_id)]


@router.get("/{business_id}/rules", response_model=List[CategoryRuleOut])
def list_category_rules(
    business_id: str,
    active_only: bool = False,
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return [
        CategoryRuleOut(**item)
        for item in categorize_service.list_category_rules(
            db,
            business_id,
            active_only=active_only,
            limit=limit,
            offset=offset,
        )
    ]


@router.post("/business/{business_id}/rules", response_model=CategoryRuleOut)
def create_category_rule(business_id: str, req: CategoryRuleIn, db: Session = Depends(get_db)):
    return CategoryRuleOut(**categorize_service.create_category_rule(db, business_id, req))


@router.patch("/{business_id}/rules/{rule_id}", response_model=CategoryRuleOut)
def update_category_rule(
    business_id: str,
    rule_id: str,
    req: CategoryRulePatch,
    db: Session = Depends(get_db),
):
    return CategoryRuleOut(**categorize_service.update_category_rule(db, business_id, rule_id, req))


@router.delete("/{business_id}/rules/{rule_id}")
def delete_category_rule(
    business_id: str,
    rule_id: str,
    db: Session = Depends(get_db),
):
    return categorize_service.delete_category_rule(db, business_id, rule_id)


@router.get("/{business_id}/rules/{rule_id}/preview", response_model=CategoryRulePreviewOut)
def preview_category_rule(
    business_id: str,
    rule_id: str,
    include_posted: bool = Query(False),
    db: Session = Depends(get_db),
):
    return CategoryRulePreviewOut(
        **categorize_service.preview_category_rule(
            db,
            business_id,
            rule_id,
            include_posted=include_posted,
        )
    )


@router.post("/{business_id}/rules/{rule_id}/apply", response_model=CategoryRuleApplyOut)
def apply_category_rule(
    business_id: str,
    rule_id: str,
    db: Session = Depends(get_db),
):
    return CategoryRuleApplyOut(**categorize_service.apply_category_rule(db, business_id, rule_id))


@router.post("/business/{business_id}/categorize")
def upsert_categorization(business_id: str, req: CategorizationUpsertIn, db: Session = Depends(get_db)):
    return categorize_service.upsert_categorization(db, business_id, req)


@router.post("/business/{business_id}/categorize/bulk_apply")
def bulk_apply_categorization(
    business_id: str,
    req: BulkCategorizationIn,
    db: Session = Depends(get_db),
):
    return categorize_service.bulk_apply_categorization(db, business_id, req)


@router.get("/business/{business_id}/categorize/metrics", response_model=CategorizationMetricsOut)
def categorization_metrics(business_id: str, db: Session = Depends(get_db)):
    return CategorizationMetricsOut(**categorize_service.categorization_metrics(db, business_id))
