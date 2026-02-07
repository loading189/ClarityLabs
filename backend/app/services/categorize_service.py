from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import HTTPException
from sqlalchemy import select, and_, inspect
from sqlalchemy.orm import Session, load_only

from backend.app.models import (
    Business,
    Category,
    TxnCategorization,
    BusinessCategoryMap,
    CategoryRule,
    utcnow,
)
from backend.app.norma.category_engine import suggest_category
from backend.app.norma.merchant import merchant_key, canonical_merchant_name
from backend.app.norma.categorize_brain import brain
from backend.app.services.category_seed import seed_coa_and_categories_and_mappings
from backend.app.services.category_resolver import resolve_system_key
from backend.app.services.posted_txn_service import posted_txns


def require_business(db: Session, business_id: str) -> Business:
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(404, "business not found")
    return biz


def require_category(db: Session, business_id: str, category_id: str) -> Category:
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


def _find_posted_txn(db: Session, business_id: str, source_event_id: str):
    for item in posted_txns(db, business_id, include_removed=True):
        if item.canonical_source_event_id == source_event_id or item.raw_event.source_event_id == source_event_id:
            return item
    return None


def system_key_for_category(db: Session, business_id: str, category_id: str) -> Optional[str]:
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


def _category_rule_column_names(db: Session) -> set[str]:
    inspector = inspect(db.get_bind())
    return {col["name"] for col in inspector.get_columns(CategoryRule.__tablename__)}


def _category_rule_load_columns(
    db: Session,
    *,
    include_optional: bool = False,
) -> tuple[list, set[str]]:
    names = [
        "id",
        "business_id",
        "category_id",
        "contains_text",
        "direction",
        "account",
        "priority",
        "active",
        "created_at",
    ]
    if include_optional:
        names.extend(["last_run_at", "last_run_updated_count"])
    column_names = _category_rule_column_names(db)
    attrs = [getattr(CategoryRule, name) for name in names if name in column_names]
    return attrs, column_names


def _brain_alias_keys_for_merchant(merchant_id: str) -> List[str]:
    return sorted(
        [alias.alias_key for alias in brain.aliases.values() if alias.merchant_id == merchant_id]
    )


def _brain_vendor_out(
    *,
    merchant_id: str,
    label,
    merchant_key_value: Optional[str] = None,
) -> Dict[str, Any]:
    merchant = brain.get_merchant(merchant_id)
    canonical = merchant.canonical_name if merchant else "Unknown"
    return {
        "merchant_id": merchant_id,
        "canonical_name": canonical,
        "system_key": label.system_key,
        "confidence": label.confidence,
        "evidence_count": label.evidence_count,
        "updated_at": label.updated_at,
        "alias_keys": _brain_alias_keys_for_merchant(merchant_id),
        "merchant_key": merchant_key_value,
    }


def label_vendor(db: Session, business_id: str, req) -> Dict[str, Any]:
    require_business(db, business_id)

    seed_coa_and_categories_and_mappings(db, business_id)

    item = _find_posted_txn(db, business_id, req.source_event_id)
    if not item:
        raise HTTPException(404, "raw event not found")

    txn = item.txn
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


def list_brain_vendors(db: Session, business_id: str) -> List[Dict[str, Any]]:
    require_business(db, business_id)

    labels = brain.labels.get(business_id, {})
    vendors: List[Dict[str, Any]] = []
    for merchant_id, label in labels.items():
        system_key = (label.system_key or "").strip().lower()
        if not system_key or system_key == "uncategorized":
            continue
        vendors.append(_brain_vendor_out(merchant_id=merchant_id, label=label))

    vendors.sort(key=lambda v: (v.get("canonical_name") or "").lower())
    return vendors


def get_brain_vendor(db: Session, business_id: str, merchant_key_value: str) -> Dict[str, Any]:
    require_business(db, business_id)

    alias_key = merchant_key_value.strip() if merchant_key_value else ""
    alias_key = merchant_key(alias_key) if alias_key else ""
    if not alias_key:
        raise HTTPException(400, "merchant_key required")

    merchant_id = brain.resolve_merchant_id(alias_key)
    if not merchant_id:
        raise HTTPException(404, "vendor not found")

    label = brain.labels.get(business_id, {}).get(merchant_id)
    if not label or (label.system_key or "").strip().lower() == "uncategorized":
        raise HTTPException(404, "vendor not found")

    return _brain_vendor_out(
        merchant_id=merchant_id,
        label=label,
        merchant_key_value=alias_key,
    )


def set_brain_vendor(db: Session, business_id: str, req) -> Dict[str, Any]:
    require_business(db, business_id)
    seed_coa_and_categories_and_mappings(db, business_id)
    require_category(db, business_id, req.category_id)

    alias_key = merchant_key(req.merchant_key or "")
    if not alias_key:
        raise HTTPException(400, "merchant_key required")

    system_key = system_key_for_category(db, business_id, req.category_id)
    if not system_key or system_key == "uncategorized":
        raise HTTPException(400, "category must map to a valid system_key")

    canonical = canonical_merchant_name(req.canonical_name or alias_key or "Unknown")
    confidence = 0.92

    label = brain.apply_label(
        business_id=business_id,
        alias_key=alias_key,
        canonical_name=canonical,
        system_key=system_key,
        confidence=confidence,
    )
    brain.save()

    return _brain_vendor_out(
        merchant_id=label.merchant_id,
        label=label,
        merchant_key_value=alias_key,
    )


def forget_brain_vendor(db: Session, business_id: str, req) -> Dict[str, Any]:
    require_business(db, business_id)

    alias_key = merchant_key(req.merchant_key or "")
    if not alias_key:
        raise HTTPException(400, "merchant_key required")

    merchant_id = brain.resolve_merchant_id(alias_key)
    if not merchant_id:
        return {"status": "ok", "deleted": False}

    per = brain.labels.get(business_id)
    if not per:
        return {"status": "ok", "deleted": False}

    deleted = per.pop(merchant_id, None) is not None
    if deleted:
        brain.save()

    return {"status": "ok", "deleted": deleted}


def list_txns_to_categorize(
    db: Session,
    business_id: str,
    limit: int,
    only_uncategorized: bool,
) -> List[Dict[str, Any]]:
    require_business(db, business_id)
    seed_coa_and_categories_and_mappings(db, business_id)

    rows = posted_txns(db, business_id, limit=500)

    existing = db.execute(
        select(TxnCategorization.source_event_id).where(TxnCategorization.business_id == business_id)
    ).scalars().all()
    existing_set = set(existing)

    out: List[Dict[str, Any]] = []

    for item in rows:
        if only_uncategorized and item.canonical_source_event_id in existing_set:
            continue

        txn = item.txn
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
            {
                "source_event_id": item.canonical_source_event_id,
                "occurred_at": item.raw_event.occurred_at,
                "description": txn.description,
                "amount": txn.amount,
                "direction": txn.direction,
                "account": txn.account,
                "category_hint": txn.category,
                "suggested_system_key": system_key,
                "suggestion_source": suggestion_source,
                "confidence": confidence,
                "reason": reason,
                "suggested_category_id": suggested_category_id,
                "suggested_category_name": suggested_category_name,
                "merchant_key": mk,
            }
        )

        if len(out) >= limit:
            break

    return out


def list_categories(db: Session, business_id: str) -> List[Dict[str, Any]]:
    require_business(db, business_id)
    seed_coa_and_categories_and_mappings(db, business_id)

    cats = db.execute(
        select(Category).where(Category.business_id == business_id).order_by(Category.name.asc())
    ).scalars().all()

    return [
        {
            "id": c.id,
            "name": c.name,
            "system_key": getattr(c, "system_key", None),
            "account_id": c.account_id,
            "account_code": c.account.code if getattr(c, "account", None) else None,
            "account_name": c.account.name if getattr(c, "account", None) else "",
        }
        for c in cats
    ]


def _category_rule_out(rule: CategoryRule, column_names: set[str]) -> Dict[str, Any]:
    return {
        "id": rule.id,
        "business_id": rule.business_id,
        "category_id": rule.category_id,
        "contains_text": rule.contains_text,
        "direction": rule.direction,
        "account": rule.account,
        "priority": rule.priority,
        "active": rule.active,
        "created_at": rule.created_at,
        "last_run_at": rule.last_run_at if "last_run_at" in column_names else None,
        "last_run_updated_count": (
            rule.last_run_updated_count if "last_run_updated_count" in column_names else None
        ),
    }


def _rule_order_key(rule: CategoryRule) -> tuple:
    return (rule.priority, rule.created_at, rule.id)


def _ordered_active_rules(db: Session, business_id: str) -> List[CategoryRule]:
    load_columns, _column_names = _category_rule_load_columns(db)
    return (
        db.execute(
            select(CategoryRule)
            .options(load_only(*load_columns))
            .where(
                and_(
                    CategoryRule.business_id == business_id,
                    CategoryRule.active.is_(True),
                )
            )
            .order_by(
                CategoryRule.priority.asc(),
                CategoryRule.created_at.asc(),
                CategoryRule.id.asc(),
            )
        )
        .scalars()
        .all()
    )


def _rule_matches(rule: CategoryRule, txn) -> bool:
    desc = (txn.description or "").strip().lower()
    if not desc:
        return False
    needle = (rule.contains_text or "").strip().lower()
    if not needle:
        return False
    if needle not in desc:
        return False
    direction = (txn.direction or "").strip().lower()
    account = (txn.account or "").strip().lower()
    if rule.direction and rule.direction.strip().lower() != direction:
        return False
    if rule.account and rule.account.strip().lower() != account:
        return False
    return True


def _first_matching_rule(rules: List[CategoryRule], txn) -> Optional[CategoryRule]:
    for rule in rules:
        if _rule_matches(rule, txn):
            return rule
    return None


def list_category_rules(
    db: Session,
    business_id: str,
    *,
    active_only: bool = False,
    limit: int = 200,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    require_business(db, business_id)

    load_columns, column_names = _category_rule_load_columns(db, include_optional=True)
    query = select(CategoryRule).where(CategoryRule.business_id == business_id)
    if active_only:
        query = query.where(CategoryRule.active.is_(True))

    rules = (
        db.execute(
            query.options(load_only(*load_columns)).order_by(
                CategoryRule.priority.asc(),
                CategoryRule.created_at.asc(),
                CategoryRule.id.asc(),
            )
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )

    return [_category_rule_out(rule, column_names) for rule in rules]


def create_category_rule(db: Session, business_id: str, req) -> Dict[str, Any]:
    require_business(db, business_id)
    seed_coa_and_categories_and_mappings(db, business_id)
    require_category(db, business_id, req.category_id)

    system_key = system_key_for_category(db, business_id, req.category_id)
    if not system_key or system_key == "uncategorized":
        raise HTTPException(400, "category must map to a valid system_key")

    contains_text = (req.contains_text or "").strip().lower()
    if not contains_text:
        raise HTTPException(400, "contains_text required")

    direction = (req.direction or "").strip().lower() or None
    account = (req.account or "").strip().lower() or None
    priority = int(req.priority) if req.priority is not None else 100
    active = bool(req.active) if req.active is not None else True

    rule = CategoryRule(
        business_id=business_id,
        category_id=req.category_id,
        contains_text=contains_text,
        direction=direction,
        account=account,
        priority=priority,
        active=active,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)

    column_names = _category_rule_column_names(db)
    return _category_rule_out(rule, column_names)


def update_category_rule(db: Session, business_id: str, rule_id: str, req) -> Dict[str, Any]:
    require_business(db, business_id)

    load_columns, column_names = _category_rule_load_columns(db, include_optional=True)
    rule = db.execute(
        select(CategoryRule)
        .options(load_only(*load_columns))
        .where(and_(CategoryRule.business_id == business_id, CategoryRule.id == rule_id))
    ).scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "rule not found")

    if req.category_id is not None:
        require_category(db, business_id, req.category_id)
        system_key = system_key_for_category(db, business_id, req.category_id)
        if not system_key or system_key == "uncategorized":
            raise HTTPException(400, "category must map to a valid system_key")
        rule.category_id = req.category_id

    if req.contains_text is not None:
        contains_text = (req.contains_text or "").strip().lower()
        if not contains_text:
            raise HTTPException(400, "contains_text required")
        rule.contains_text = contains_text

    if req.direction is not None:
        rule.direction = (req.direction or "").strip().lower() or None

    if req.account is not None:
        rule.account = (req.account or "").strip().lower() or None

    if req.priority is not None:
        rule.priority = int(req.priority)

    if req.active is not None:
        rule.active = bool(req.active)

    db.add(rule)
    db.commit()
    db.refresh(rule)

    return _category_rule_out(rule, column_names)


def delete_category_rule(db: Session, business_id: str, rule_id: str) -> Dict[str, Any]:
    require_business(db, business_id)
    load_columns, _column_names = _category_rule_load_columns(db)
    rule = db.execute(
        select(CategoryRule)
        .options(load_only(*load_columns))
        .where(and_(CategoryRule.business_id == business_id, CategoryRule.id == rule_id))
    ).scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "rule not found")

    db.delete(rule)
    db.commit()

    return {"deleted": True}


def preview_category_rule(
    db: Session,
    business_id: str,
    rule_id: str,
    *,
    sample_limit: int = 10,
    max_events: int = 5000,
) -> Dict[str, Any]:
    """
    Preview a single rule using the same conflict policy as the rules engine.
    Only uncategorized transactions are considered.
    """
    require_business(db, business_id)

    load_columns, _column_names = _category_rule_load_columns(db)
    rule = db.execute(
        select(CategoryRule)
        .options(load_only(*load_columns))
        .where(and_(CategoryRule.business_id == business_id, CategoryRule.id == rule_id))
    ).scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "rule not found")

    rules = _ordered_active_rules(db, business_id)
    if not any(r.id == rule.id for r in rules):
        rules.append(rule)
        rules.sort(key=_rule_order_key)

    existing_ids = set(
        db.execute(
            select(TxnCategorization.source_event_id).where(TxnCategorization.business_id == business_id)
        ).scalars().all()
    )

    rows = posted_txns(db, business_id, limit=max_events)

    matched = 0
    samples: List[Dict[str, Any]] = []

    for item in rows:
        if item.canonical_source_event_id in existing_ids:
            continue
        txn = item.txn
        winner = _first_matching_rule(rules, txn)
        if not winner or winner.id != rule.id:
            continue
        matched += 1
        if len(samples) < sample_limit:
            samples.append(
                {
                    "source_event_id": txn.source_event_id,
                    "occurred_at": item.raw_event.occurred_at,
                    "description": txn.description,
                    "amount": txn.amount,
                    "direction": txn.direction,
                    "account": txn.account,
                }
            )

    return {"rule_id": rule.id, "matched": matched, "samples": samples}


def apply_category_rule(db: Session, business_id: str, rule_id: str) -> Dict[str, Any]:
    """
    Apply a single rule to uncategorized transactions only.
    """
    require_business(db, business_id)

    load_columns, column_names = _category_rule_load_columns(db, include_optional=True)
    rule = db.execute(
        select(CategoryRule)
        .options(load_only(*load_columns))
        .where(and_(CategoryRule.business_id == business_id, CategoryRule.id == rule_id))
    ).scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "rule not found")

    rules = _ordered_active_rules(db, business_id)
    if not any(r.id == rule.id for r in rules):
        rules.append(rule)
        rules.sort(key=_rule_order_key)

    existing_ids = set(
        db.execute(
            select(TxnCategorization.source_event_id).where(TxnCategorization.business_id == business_id)
        ).scalars().all()
    )

    rows = posted_txns(db, business_id, limit=5000)

    matched_ids: List[str] = []
    for item in rows:
        if item.canonical_source_event_id in existing_ids:
            continue
        txn = item.txn
        winner = _first_matching_rule(rules, txn)
        if winner and winner.id == rule.id:
            matched_ids.append(item.canonical_source_event_id)

    updated = 0
    for source_event_id in matched_ids:
        row = TxnCategorization(
            business_id=business_id,
            source_event_id=source_event_id,
            category_id=rule.category_id,
            source="rule",
            confidence=0.92,
            note=None,
        )
        db.add(row)
        updated += 1

    if "last_run_at" in column_names:
        rule.last_run_at = utcnow()
    if "last_run_updated_count" in column_names:
        rule.last_run_updated_count = updated
    db.add(rule)
    db.commit()

    return {"rule_id": rule.id, "matched": len(matched_ids), "updated": updated}


def upsert_categorization(db: Session, business_id: str, req) -> Dict[str, Any]:
    require_business(db, business_id)
    seed_coa_and_categories_and_mappings(db, business_id)
    require_category(db, business_id, req.category_id)

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

    item = _find_posted_txn(db, business_id, req.source_event_id)

    if item:
        txn = item.txn
        mk = merchant_key(txn.description)
        system_key = system_key_for_category(db, business_id, req.category_id)

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


def bulk_apply_categorization(db: Session, business_id: str, req) -> Dict[str, Any]:
    require_business(db, business_id)
    seed_coa_and_categories_and_mappings(db, business_id)
    require_category(db, business_id, req.category_id)

    system_key = system_key_for_category(db, business_id, req.category_id)
    if not system_key or system_key == "uncategorized":
        raise HTTPException(400, "category must map to a valid system_key")

    target_key = merchant_key(req.merchant_key)
    if not target_key:
        raise HTTPException(400, "merchant_key required")

    rows = posted_txns(db, business_id, limit=5000)

    matching_ids: List[str] = []
    for item in rows:
        txn = item.txn
        if merchant_key(txn.description) == target_key:
            matching_ids.append(item.canonical_source_event_id)

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
            continue
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


def categorization_metrics(db: Session, business_id: str) -> Dict[str, Any]:
    require_business(db, business_id)
    seed_coa_and_categories_and_mappings(db, business_id)

    total_events = posted_txns(db, business_id)
    total_count = len(total_events)

    categorized_ids = set(
        db.execute(
            select(TxnCategorization.source_event_id).where(TxnCategorization.business_id == business_id)
        ).scalars().all()
    )

    posted = len(categorized_ids)
    uncategorized = max(0, total_count - posted)

    suggestion_coverage = 0
    for item in total_events:
        if item.canonical_source_event_id in categorized_ids:
            continue
        txn = item.txn
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

    return {
        "total_events": total_count,
        "posted": posted,
        "uncategorized": uncategorized,
        "suggestion_coverage": suggestion_coverage,
        "brain_coverage": brain_coverage,
    }
