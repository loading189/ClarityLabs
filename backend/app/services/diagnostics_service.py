from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import HTTPException
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from backend.app.models import (
    Account,
    Business,
    BusinessCategoryMap,
    Category,
    CategoryRule,
    RawEvent,
    TxnCategorization,
)
from backend.app.norma.from_events import raw_event_to_txn
from backend.app.norma.ledger import LedgerIntegrityError, build_cash_ledger, check_ledger_integrity
from backend.app.norma.normalize import NormalizedTransaction
from backend.app.services.category_resolver import resolve_system_key
from backend.app.norma.categorize_brain import brain

logger = logging.getLogger(__name__)


def require_business(db: Session, business_id: str) -> Business:
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(404, "business not found")
    return biz


def _fetch_posted_transactions(db: Session, business_id: str) -> List[NormalizedTransaction]:
    stmt = (
        select(TxnCategorization, RawEvent, Category, Account)
        .join(
            RawEvent,
            and_(
                RawEvent.business_id == TxnCategorization.business_id,
                RawEvent.source_event_id == TxnCategorization.source_event_id,
            ),
        )
        .join(Category, Category.id == TxnCategorization.category_id)
        .join(Account, Account.id == Category.account_id)
        .where(TxnCategorization.business_id == business_id)
        .order_by(RawEvent.occurred_at.asc(), RawEvent.source_event_id.asc())
    )

    rows = db.execute(stmt).all()
    txns: List[NormalizedTransaction] = []
    for _, ev, cat, acct in rows:
        txn = raw_event_to_txn(ev.payload, ev.occurred_at, ev.source_event_id)
        txns.append(
            NormalizedTransaction(
                id=txn.id,
                source_event_id=txn.source_event_id,
                occurred_at=txn.occurred_at,
                date=txn.date,
                description=txn.description,
                amount=txn.amount,
                direction=txn.direction,
                account=acct.name,
                category=(cat.name or cat.system_key or "uncategorized"),
                counterparty_hint=txn.counterparty_hint,
            )
        )

    return txns


def collect_diagnostics(db: Session, business_id: str) -> Dict[str, Any]:
    require_business(db, business_id)

    categories = db.execute(
        select(Category).where(Category.business_id == business_id)
    ).scalars().all()
    accounts = db.execute(
        select(Account.id).where(Account.business_id == business_id)
    ).scalars().all()
    account_ids = set(accounts)

    orphan_categories = []
    for cat in categories:
        if not cat.account_id or cat.account_id not in account_ids:
            orphan_categories.append(
                {
                    "category_id": cat.id,
                    "name": cat.name,
                    "account_id": cat.account_id,
                }
            )

    if orphan_categories:
        logger.warning(
            "[diagnostics] orphan categories business=%s count=%s",
            business_id,
            len(orphan_categories),
        )

    mapping_category_ids = set(
        db.execute(
            select(BusinessCategoryMap.category_id).where(
                BusinessCategoryMap.business_id == business_id
            )
        ).scalars().all()
    )
    category_by_id = {cat.id: cat for cat in categories}

    invalid_rule_outputs: List[Dict[str, Any]] = []
    rules = db.execute(
        select(CategoryRule).where(CategoryRule.business_id == business_id)
    ).scalars().all()
    for rule in rules:
        cat = category_by_id.get(rule.category_id)
        if not cat:
            invalid_rule_outputs.append(
                {
                    "rule_id": rule.id,
                    "category_id": rule.category_id,
                    "issue": "missing_category",
                }
            )
            continue
        if not cat.account_id or cat.account_id not in account_ids:
            invalid_rule_outputs.append(
                {
                    "rule_id": rule.id,
                    "category_id": rule.category_id,
                    "issue": "missing_account",
                }
            )
        elif cat.id not in mapping_category_ids:
            invalid_rule_outputs.append(
                {
                    "rule_id": rule.id,
                    "category_id": rule.category_id,
                    "issue": "missing_system_key_mapping",
                }
            )

    if invalid_rule_outputs:
        logger.warning(
            "[diagnostics] invalid rule outputs business=%s count=%s",
            business_id,
            len(invalid_rule_outputs),
        )

    invalid_vendor_defaults: List[Dict[str, Any]] = []
    labels = brain.labels.get(business_id, {})
    for merchant_id, label in labels.items():
        system_key = (label.system_key or "").strip().lower()
        if not system_key or system_key == "uncategorized":
            invalid_vendor_defaults.append(
                {
                    "merchant_id": merchant_id,
                    "system_key": system_key,
                    "issue": "empty_system_key",
                }
            )
            continue
        resolved = resolve_system_key(db, business_id, system_key)
        if not resolved:
            invalid_vendor_defaults.append(
                {
                    "merchant_id": merchant_id,
                    "system_key": system_key,
                    "issue": "missing_system_key_mapping",
                }
            )

    if invalid_vendor_defaults:
        logger.warning(
            "[diagnostics] invalid vendor defaults business=%s count=%s",
            business_id,
            len(invalid_vendor_defaults),
        )

    ledger_integrity: Dict[str, Any]
    txns = _fetch_posted_transactions(db, business_id)
    if not txns:
        ledger_integrity = {
            "status": "insufficient_data",
            "detail": "No posted transactions to validate ledger integrity.",
        }
    else:
        try:
            ledger = build_cash_ledger(txns, opening_balance=0.0)
            summary = check_ledger_integrity(ledger, opening_balance=0.0)
            ledger_integrity = {"status": "ok", "summary": summary}
        except LedgerIntegrityError as exc:
            logger.warning(
                "[diagnostics] ledger integrity violation business=%s error=%s",
                business_id,
                str(exc),
            )
            ledger_integrity = {"status": "error", "detail": str(exc)}

    return {
        "orphan_categories": orphan_categories,
        "invalid_rule_outputs": invalid_rule_outputs,
        "invalid_vendor_defaults": invalid_vendor_defaults,
        "ledger_integrity": ledger_integrity,
    }
