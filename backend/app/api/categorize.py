from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.models import Business, RawEvent, Category, TxnCategorization, BusinessCategoryMap
from backend.app.norma.from_events import raw_event_to_txn
from backend.app.norma.category_engine import suggest_category
from backend.app.norma.merchant import merchant_key, canonical_merchant_name
from backend.app.norma.categorize_brain import brain
from backend.app.services.category_seed import seed_coa_and_categories_and_mappings
from backend.app.services.category_resolver import resolve_system_key

router = APIRouter(prefix="/categorize", tags=["categorize"])


def _require_business(db: Session, business_id: str) -> Business:
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(404, "business not found")
    return biz


def _system_key_for_category(db: Session, business_id: str, category_id: str) -> Optional[str]:
    # If multiple mappings exist, prefer "curated" ones (not acct_ fallback).
    rows = db.execute(
        select(BusinessCategoryMap.system_key).where(
            and_(
                BusinessCategoryMap.business_id == business_id,
                BusinessCategoryMap.category_id == category_id,
            )
        )
    ).scalars().all()

    if not rows:
        return None

    # Prefer non-fallback keys first
    curated = [r for r in rows if not (r or "").startswith("acct_")]
    pick = curated[0] if curated else rows[0]

    return (pick or "").strip().lower() or None


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


class LabelVendorIn(BaseModel):
    source_event_id: str
    system_key: str
    canonical_name: Optional[str] = None
    confidence: float = 0.92


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


@router.post("/business/{business_id}/label_vendor")
def label_vendor(business_id: str, req: LabelVendorIn, db: Session = Depends(get_db)):
    _require_business(db, business_id)

    seed_coa_and_categories_and_mappings(db, business_id)

    ev = db.execute(
        select(RawEvent).where(
            and_(RawEvent.business_id == business_id, RawEvent.source_event_id == req.source_event_id)
        )
    ).scalar_one_or_none()
    if not ev:
        raise HTTPException(404, "raw event not found")

    txn = raw_event_to_txn(ev.payload, ev.occurred_at, ev.source_event_id)
    mk = merchant_key(txn.description)

    system_key = (req.system_key or "").strip().lower()
    if not system_key:
        raise HTTPException(400, "system_key required")

    canon = canonical_merchant_name(req.canonical_name or txn.description or "Unknown")

    lbl = brain.apply_label(
        business_id=business_id,
        alias_key=mk,
        canonical_name=canon,
        system_key=system_key,
        confidence=req.confidence,
    )
    brain.save()

    resolved = resolve_system_key(db, business_id, system_key)

    return {
        "status": "ok",
        "merchant_key": mk,
        "system_key": system_key,
        "confidence": lbl.confidence,
        "evidence_count": lbl.evidence_count,
        "resolved": bool(resolved),
        **(resolved or {}),
    }


@router.get("/business/{business_id}/txns", response_model=List[NormalizedTxnOut])
def list_txns_to_categorize(
    business_id: str,
    limit: int = Query(50, ge=1, le=200),
    only_uncategorized: bool = True,
    db: Session = Depends(get_db),
):
    _require_business(db, business_id)
    seed_coa_and_categories_and_mappings(db, business_id)

    rows = db.execute(
        select(RawEvent)
        .where(RawEvent.business_id == business_id)
        .order_by(RawEvent.occurred_at.desc())
        .limit(500)
    ).scalars().all()

    existing = db.execute(
        select(TxnCategorization.source_event_id).where(TxnCategorization.business_id == business_id)
    ).scalars().all()
    existing_set = set(existing)

    out: List[NormalizedTxnOut] = []

    for ev in rows:
        if only_uncategorized and ev.source_event_id in existing_set:
            continue

        txn = raw_event_to_txn(ev.payload, ev.occurred_at, ev.source_event_id)
        suggested = suggest_category(db, txn, business_id=business_id)

        cat_obj = getattr(suggested, "categorization", None)

        mk = merchant_key(txn.description)

        system_key: Optional[str] = None
        suggestion_source: Optional[str] = None
        confidence: Optional[float] = None
        reason: Optional[str] = None
        suggested_category_id: Optional[str] = None
        suggested_category_name: Optional[str] = None

        if cat_obj:
            candidate = (cat_obj.category or "").strip().lower()

            # ✅ never suggest uncategorized
            if candidate and candidate != "uncategorized":
                resolved = resolve_system_key(db, business_id, candidate)

                # ✅ only suggest if it maps to a real Category in the dropdown
                if resolved:
                    system_key = candidate
                    suggestion_source = (cat_obj.source or "rule").strip().lower()
                    confidence = float(cat_obj.confidence or 0.0)
                    reason = cat_obj.reason or "—"

                    suggested_category_id = resolved["category_id"]
                    suggested_category_name = resolved["category_name"]


        out.append(
            NormalizedTxnOut(
                source_event_id=txn.source_event_id,
                occurred_at=txn.occurred_at,
                description=txn.description,
                amount=txn.amount,
                direction=txn.direction,
                account=txn.account,
                category_hint=txn.category,
                suggested_system_key=system_key,
                suggestion_source=suggestion_source,
                confidence=confidence,
                reason=reason,
                suggested_category_id=suggested_category_id,
                suggested_category_name=suggested_category_name,
                merchant_key=mk,
            )
        )

        if len(out) >= limit:
            break

    return out


def _require_category(db: Session, business_id: str, category_id: str) -> Category:
    cat = db.execute(
        select(Category).where(
            and_(
                Category.business_id == business_id,
                Category.id == category_id,
            )
        )
    ).scalar_one_or_none()
    if not cat or not cat.account_id:
        raise HTTPException(404, "category not found for business")
    return cat


@router.get("/business/{business_id}/categories", response_model=List[CategoryOut])
def list_categories(business_id: str, db: Session = Depends(get_db)):
    _require_business(db, business_id)
    seed_coa_and_categories_and_mappings(db, business_id)

    cats = db.execute(
        select(Category).where(Category.business_id == business_id).order_by(Category.name.asc())
    ).scalars().all()

    return [
        CategoryOut(
            id=c.id,
            name=c.name,
            system_key=getattr(c, "system_key", None),
            account_id=c.account_id,
            account_code=c.account.code if getattr(c, "account", None) else None,
            account_name=c.account.name if getattr(c, "account", None) else "",
        )
        for c in cats
    ]


@router.post("/business/{business_id}/categorize")
def upsert_categorization(business_id: str, req: CategorizationUpsertIn, db: Session = Depends(get_db)):
    _require_business(db, business_id)
    seed_coa_and_categories_and_mappings(db, business_id)
    _require_category(db, business_id, req.category_id)

    existing = db.execute(
        select(TxnCategorization).where(
            and_(
                TxnCategorization.business_id == business_id,
                TxnCategorization.source_event_id == req.source_event_id,
            )
        )
    ).scalar_one_or_none()

    if existing:
        existing.category_id = req.category_id
        existing.source = req.source
        existing.confidence = req.confidence
        existing.note = req.note
        db.add(existing)
        db.commit()
        updated = True
    else:
        row = TxnCategorization(
            business_id=business_id,
            source_event_id=req.source_event_id,
            category_id=req.category_id,
            source=req.source,
            confidence=req.confidence,
            note=req.note,
        )
        db.add(row)
        db.commit()
        updated = False

    learned = False
    learned_system_key: Optional[str] = None

    ev = db.execute(
        select(RawEvent).where(
            and_(RawEvent.business_id == business_id, RawEvent.source_event_id == req.source_event_id)
        )
    ).scalar_one_or_none()

    if ev:
        txn = raw_event_to_txn(ev.payload, ev.occurred_at, ev.source_event_id)
        mk = merchant_key(txn.description)
        system_key = _system_key_for_category(db, business_id, req.category_id)

        if system_key and system_key != "uncategorized":
            canon = canonical_merchant_name(txn.description or "Unknown")
            brain.apply_label(
                business_id=business_id,
                alias_key=mk,
                canonical_name=canon,
                system_key=system_key,
                confidence=min(1.0, float(req.confidence or 1.0)),
            )
            brain.save()
            learned = True
            learned_system_key = system_key

    return {
        "status": "ok",
        "updated": updated,
        "learned": learned,
        "learned_system_key": learned_system_key,
    }


@router.post("/business/{business_id}/categorize/bulk_apply")
def bulk_apply_categorization(
    business_id: str,
    req: BulkCategorizationIn,
    db: Session = Depends(get_db),
):
    _require_business(db, business_id)
    seed_coa_and_categories_and_mappings(db, business_id)
    _require_category(db, business_id, req.category_id)

    target_key = merchant_key(req.merchant_key)
    if not target_key:
        raise HTTPException(400, "merchant_key required")

    rows = db.execute(
        select(RawEvent)
        .where(RawEvent.business_id == business_id)
        .order_by(RawEvent.occurred_at.desc())
        .limit(5000)
    ).scalars().all()

    matching_ids: List[str] = []
    for ev in rows:
        txn = raw_event_to_txn(ev.payload, ev.occurred_at, ev.source_event_id)
        if merchant_key(txn.description) == target_key:
            matching_ids.append(ev.source_event_id)

    if not matching_ids:
        return {
            "status": "ok",
            "matched_events": 0,
            "created": 0,
            "updated": 0,
        }

    existing = db.execute(
        select(TxnCategorization).where(
            and_(
                TxnCategorization.business_id == business_id,
                TxnCategorization.source_event_id.in_(matching_ids),
            )
        )
    ).scalars().all()
    existing_map = {row.source_event_id: row for row in existing}

    created = 0
    updated = 0
    for source_event_id in matching_ids:
        row = existing_map.get(source_event_id)
        if row:
            row.category_id = req.category_id
            row.source = req.source
            row.confidence = req.confidence
            row.note = req.note
            db.add(row)
            updated += 1
        else:
            row = TxnCategorization(
                business_id=business_id,
                source_event_id=source_event_id,
                category_id=req.category_id,
                source=req.source,
                confidence=req.confidence,
                note=req.note,
            )
            db.add(row)
            created += 1

    db.commit()

    return {
        "status": "ok",
        "matched_events": len(matching_ids),
        "created": created,
        "updated": updated,
    }


@router.get("/business/{business_id}/categorize/metrics", response_model=CategorizationMetricsOut)
def categorization_metrics(business_id: str, db: Session = Depends(get_db)):
    _require_business(db, business_id)
    seed_coa_and_categories_and_mappings(db, business_id)

    total_events = db.execute(
        select(RawEvent).where(RawEvent.business_id == business_id)
    ).scalars().all()
    total_count = len(total_events)

    categorized_ids = set(
        db.execute(
            select(TxnCategorization.source_event_id).where(TxnCategorization.business_id == business_id)
        ).scalars().all()
    )

    posted = len(categorized_ids)
    uncategorized = max(0, total_count - posted)

    suggestion_coverage = 0
    for ev in total_events:
        if ev.source_event_id in categorized_ids:
            continue
        txn = raw_event_to_txn(ev.payload, ev.occurred_at, ev.source_event_id)
        suggested = suggest_category(db, txn, business_id=business_id)
        cat_obj = getattr(suggested, "categorization", None)
        if not cat_obj:
            continue
        candidate = (cat_obj.category or "").strip().lower()
        if not candidate or candidate == "uncategorized":
            continue
        if resolve_system_key(db, business_id, candidate):
            suggestion_coverage += 1

    brain_coverage = brain.count_learned_merchants(business_id)

    return CategorizationMetricsOut(
        total_events=total_count,
        posted=posted,
        uncategorized=uncategorized,
        suggestion_coverage=suggestion_coverage,
        brain_coverage=brain_coverage,
    )
