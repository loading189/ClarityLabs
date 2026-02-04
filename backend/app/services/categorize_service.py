from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import HTTPException
from sqlalchemy import select, and_, inspect
from sqlalchemy.orm import Session, load_only

from backend.app.models import (
    Business,
    RawEvent,
    Category,
    TxnCategorization,
    BusinessCategoryMap,
    CategoryRule,
    Account,
    utcnow,
)
from backend.app.norma.from_events import raw_event_to_txn
from backend.app.norma.category_engine import suggest_category
from backend.app.norma.merchant import merchant_key, canonical_merchant_name
from backend.app.norma.categorize_brain import brain
from backend.app.services.category_seed import (
    seed_coa_and_categories_and_mappings,
    ensure_category_mapping_for_category,
)
from backend.app.services.category_resolver import resolve_system_key, require_system_key_mapping
from backend.app.services import audit_service



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
    acct = db.get(Account, cat.account_id)
    if not acct:
        raise HTTPException(
            409,
            f"Invariant violation: category '{category_id}' references missing account '{cat.account_id}'.",
        )

    # Ensure there is a valid system_key mapping for this category.
    # Try auto-repair once; if it can't be repaired, fail.
    if not system_key_for_category(db, business_id, category_id):
        repaired = ensure_category_mapping_for_category(db, business_id, category_id)
        if not repaired:
            raise HTTPException(409, "Invariant violation: category missing system_key mapping")

    return cat


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


def _actor_for_source(source: Optional[str]) -> str:
    if not source:
        return "user"
    key = source.strip().lower()
    if key in {"rule"}:
        return "rule"
    if key in {"system", "auto"}:
        return "system"
    if key in {"vendor"}:
        return "vendor"
    return "user"


def _category_snapshot(db: Session, category_id: str) -> Dict[str, Optional[str]]:
    cat = db.get(Category, category_id)
    return {
        "category_id": category_id,
        "category_name": cat.name if cat else None,
        "account_id": cat.account_id if cat else None,
    }


def label_vendor(db: Session, business_id: str, req) -> Dict[str, Any]:
    require_business(db, business_id)

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

    try:
        require_system_key_mapping(db, business_id, system_key, context="vendor default")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


    canon = canonical_merchant_name(req.canonical_name or txn.description or "Unknown")

    before_label = brain.lookup_label(business_id=business_id, alias_key=mk)
    lbl = brain.apply_label(
        business_id=business_id,
        alias_key=mk,
        canonical_name=canon,
        system_key=system_key,
        confidence=req.confidence,
    )
    brain.save()

    resolved = resolve_system_key(db, business_id, system_key)

    audit_service.log_audit_event(
        db,
        business_id=business_id,
        event_type="vendor_default_set",
        actor="user",
        reason="label_vendor",
        before=(
            {"system_key": before_label.system_key, "confidence": before_label.confidence}
            if before_label
            else None
        ),
        after={"system_key": system_key, "confidence": lbl.confidence},
        source_event_id=req.source_event_id,
    )
    db.commit()

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
        try:
            require_system_key_mapping(db, business_id, system_key, context="vendor default")
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
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

    try:
        require_system_key_mapping(
            db,
            business_id,
            (label.system_key or "").strip().lower(),
            context="vendor default",
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc

    return _brain_vendor_out(
        merchant_id=merchant_id,
        label=label,
        merchant_key_value=alias_key,
    )


def set_brain_vendor(db: Session, business_id: str, req) -> Dict[str, Any]:
    require_business(db, business_id)
    seed_coa_and_categories_and_mappings(db, business_id)
    require_category(db, business_id, req.category_id)
    if not system_key_for_category(db, business_id, req.category_id):
        repaired = ensure_category_mapping_for_category(db, business_id, req.category_id)
        if not repaired:
            raise HTTPException(400, "category missing account mapping")

    alias_key = merchant_key(req.merchant_key or "")
    if not alias_key:
        raise HTTPException(400, "merchant_key required")

    system_key = system_key_for_category(db, business_id, req.category_id)
    if not system_key:
        system_key = ensure_category_mapping_for_category(db, business_id, req.category_id)
    if not system_key or system_key == "uncategorized":
        raise HTTPException(400, "category must map to a valid system_key")

    canonical = canonical_merchant_name(req.canonical_name or alias_key or "Unknown")
    confidence = 0.92

    before_label = brain.lookup_label(business_id=business_id, alias_key=alias_key)
    label = brain.apply_label(
        business_id=business_id,
        alias_key=alias_key,
        canonical_name=canonical,
        system_key=system_key,
        confidence=confidence,
    )
    brain.save()

    audit_service.log_audit_event(
        db,
        business_id=business_id,
        event_type="vendor_default_set",
        actor="user",
        reason="set_vendor_default",
        before=(
            {"system_key": before_label.system_key, "confidence": before_label.confidence}
            if before_label
            else None
        ),
        after={"system_key": system_key, "confidence": label.confidence},
    )
    db.commit()

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

    before_label = per.get(merchant_id)
    deleted = per.pop(merchant_id, None) is not None
    if deleted:
        brain.save()
        audit_service.log_audit_event(
            db,
            business_id=business_id,
            event_type="vendor_default_remove",
            actor="user",
            reason="forget_vendor_default",
            before=(
                {"system_key": before_label.system_key, "confidence": before_label.confidence}
                if before_label
                else None
            ),
            after=None,
        )
        db.commit()

    return {"status": "ok", "deleted": deleted}


def list_txns_to_categorize(
    db: Session,
    business_id: str,
    limit: int,
    only_uncategorized: bool,
) -> List[Dict[str, Any]]:
    require_business(db, business_id)
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

    out: List[Dict[str, Any]] = []

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
            {
                "source_event_id": txn.source_event_id,
                "occurred_at": txn.occurred_at,
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

    missing_accounts = [c.id for c in cats if not c.account_id or not getattr(c, "account", None)]
    if missing_accounts:
        raise HTTPException(
            409,
            f"Invariant violation: categories missing account_id or account: {missing_accounts}",
        )

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
    if not system_key:
        system_key = ensure_category_mapping_for_category(db, business_id, req.category_id)
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
    audit_service.log_audit_event(
        db,
        business_id=business_id,
        event_type="rule_create",
        actor="user",
        reason="create_rule",
        before={},
        after={
            **_category_snapshot(db, rule.category_id),
            "contains_text": rule.contains_text,
            "direction": rule.direction,
            "account": rule.account,
            "priority": rule.priority,
            "active": rule.active,
        },
        rule_id=rule.id,
    )
    db.commit()
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

    before_snapshot = {
        **_category_snapshot(db, rule.category_id),
        "contains_text": rule.contains_text,
        "direction": rule.direction,
        "account": rule.account,
        "priority": rule.priority,
        "active": rule.active,
    }

    if req.category_id is not None:
        require_category(db, business_id, req.category_id)
        system_key = system_key_for_category(db, business_id, req.category_id)
        if not system_key:
            system_key = ensure_category_mapping_for_category(db, business_id, req.category_id)
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

    audit_service.log_audit_event(
        db,
        business_id=business_id,
        event_type="rule_update",
        actor="user",
        reason="update_rule",
        before=before_snapshot,
        after={
            **_category_snapshot(db, rule.category_id),
            "contains_text": rule.contains_text,
            "direction": rule.direction,
            "account": rule.account,
            "priority": rule.priority,
            "active": rule.active,
        },
        rule_id=rule.id,
    )
    db.commit()

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

    before_snapshot = {
        **_category_snapshot(db, rule.category_id),
        "contains_text": rule.contains_text,
        "direction": rule.direction,
        "account": rule.account,
        "priority": rule.priority,
        "active": rule.active,
    }

    db.delete(rule)
    db.commit()

    audit_service.log_audit_event(
        db,
        business_id=business_id,
        event_type="rule_delete",
        actor="user",
        reason="delete_rule",
        before=before_snapshot,
        after=None,
        rule_id=rule_id,
    )
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

    rows = (
        db.execute(
            select(RawEvent)
            .where(RawEvent.business_id == business_id)
            .order_by(RawEvent.occurred_at.desc(), RawEvent.source_event_id.desc())
            .limit(max_events)
        )
        .scalars()
        .all()
    )

    matched = 0
    samples: List[Dict[str, Any]] = []

    for ev in rows:
        if ev.source_event_id in existing_ids:
            continue
        txn = raw_event_to_txn(ev.payload, ev.occurred_at, ev.source_event_id)
        winner = _first_matching_rule(rules, txn)
        if not winner or winner.id != rule.id:
            continue
        matched += 1
        if len(samples) < sample_limit:
            samples.append(
                {
                    "source_event_id": txn.source_event_id,
                    "occurred_at": txn.occurred_at,
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

    if not system_key_for_category(db, business_id, rule.category_id):
        repaired = ensure_category_mapping_for_category(db, business_id, rule.category_id)
        if not repaired:
            raise HTTPException(400, "rule category missing account mapping")

    rules = _ordered_active_rules(db, business_id)
    if not any(r.id == rule.id for r in rules):
        rules.append(rule)
        rules.sort(key=_rule_order_key)

    existing_ids = set(
        db.execute(
            select(TxnCategorization.source_event_id).where(TxnCategorization.business_id == business_id)
        ).scalars().all()
    )

    rows = (
        db.execute(
            select(RawEvent)
            .where(RawEvent.business_id == business_id)
            .order_by(RawEvent.occurred_at.desc(), RawEvent.source_event_id.desc())
            .limit(5000)
        )
        .scalars()
        .all()
    )

    matched_ids: List[str] = []
    for ev in rows:
        if ev.source_event_id in existing_ids:
            continue
        txn = raw_event_to_txn(ev.payload, ev.occurred_at, ev.source_event_id)
        winner = _first_matching_rule(rules, txn)
        if winner and winner.id == rule.id:
            matched_ids.append(ev.source_event_id)

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

    before_snapshot = None
    if existing:
        before_snapshot = {
            **_category_snapshot(db, existing.category_id),
            "source": existing.source,
            "confidence": existing.confidence,
            "note": existing.note,
        }
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

    audit_row = audit_service.log_audit_event(
        db,
        business_id=business_id,
        event_type="categorization_change",
        actor=_actor_for_source(req.source),
        reason=req.note or f"source:{req.source}",
        before=before_snapshot,
        after={
            **_category_snapshot(db, req.category_id),
            "source": req.source,
            "confidence": req.confidence,
            "note": req.note,
        },
        source_event_id=req.source_event_id,
    )
    db.commit()

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
        system_key = system_key_for_category(db, business_id, req.category_id)
        if not system_key:
            system_key = ensure_category_mapping_for_category(db, business_id, req.category_id)

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
        "audit_id": audit_row.id,
    }


def bulk_apply_categorization(db: Session, business_id: str, req) -> Dict[str, Any]:
    require_business(db, business_id)
    seed_coa_and_categories_and_mappings(db, business_id)
    require_category(db, business_id, req.category_id)

    system_key = system_key_for_category(db, business_id, req.category_id)
    if not system_key:
        system_key = ensure_category_mapping_for_category(db, business_id, req.category_id)
    if not system_key or system_key == "uncategorized":
        raise HTTPException(400, "category must map to a valid system_key")

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

    audit_service.log_audit_event(
        db,
        business_id=business_id,
        event_type="categorization_change",
        actor=_actor_for_source(req.source),
        reason="bulk_apply",
        before=None,
        after={
            **_category_snapshot(db, req.category_id),
            "source": req.source,
            "confidence": req.confidence,
            "note": req.note,
            "matched_events": len(matching_ids),
            "created": created,
        },
        source_event_id=None,
    )
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

    return {
        "total_events": total_count,
        "posted": posted,
        "uncategorized": uncategorized,
        "suggestion_coverage": suggestion_coverage,
        "brain_coverage": brain_coverage,
    }
