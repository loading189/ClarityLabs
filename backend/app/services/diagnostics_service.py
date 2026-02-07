from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models import (
    Account,
    Business,
    BusinessCategoryMap,
    Category,
    CategoryRule,
    IntegrationConnection,
    RawEvent,
    TxnCategorization,
)
from backend.app.norma.ledger import LedgerIntegrityError, build_cash_ledger, check_ledger_integrity
from backend.app.norma.normalize import NormalizedTransaction
from backend.app.services.category_resolver import resolve_system_key
from backend.app.services.posted_txn_service import fetch_posted_transactions
from backend.app.services import processing_service
from backend.app.norma.categorize_brain import brain

logger = logging.getLogger(__name__)


def require_business(db: Session, business_id: str) -> Business:
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(404, "business not found")
    return biz


def _fetch_posted_transactions(db: Session, business_id: str) -> List[NormalizedTransaction]:
    return fetch_posted_transactions(db, business_id)


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


def collect_ingestion_diagnostics(db: Session, business_id: str) -> Dict[str, Any]:
    return processing_service.collect_ingestion_diagnostics(db, business_id)


def collect_reconcile_report(db: Session, business_id: str) -> Dict[str, Any]:
    require_business(db, business_id)

    raw_events_total = int(
        db.execute(
            select(func.count()).select_from(RawEvent).where(RawEvent.business_id == business_id)
        ).scalar_one()
    )
    categorized_total = int(
        db.execute(
            select(func.count())
            .select_from(TxnCategorization)
            .where(TxnCategorization.business_id == business_id)
        ).scalar_one()
    )
    posted_total = len(fetch_posted_transactions(db, business_id))

    latest_raw_event = db.execute(
        select(RawEvent.occurred_at, RawEvent.source_event_id)
        .where(RawEvent.business_id == business_id)
        .order_by(RawEvent.occurred_at.desc(), RawEvent.source_event_id.desc())
        .limit(1)
    ).first()

    connections = db.execute(
        select(IntegrationConnection).where(IntegrationConnection.business_id == business_id)
    ).scalars().all()

    connection_summaries = []
    for connection in connections:
        stale_processing = False
        if connection.last_ingested_at and connection.last_processed_at:
            stale_processing = connection.last_processed_at < connection.last_ingested_at
        elif connection.last_ingested_at and not connection.last_processed_at:
            stale_processing = True
        cursor_stale = connection.last_cursor and not connection.last_cursor_at
        connection_summaries.append(
            {
                "provider": connection.provider,
                "status": connection.status,
                "provider_cursor": connection.last_cursor,
                "provider_cursor_at": connection.last_cursor_at,
                "last_ingested_at": connection.last_ingested_at,
                "last_ingested_source_event_id": connection.last_ingested_source_event_id,
                "last_processed_at": connection.last_processed_at,
                "last_processed_source_event_id": connection.last_processed_source_event_id,
                "mismatch_flags": {
                    "processing_stale": stale_processing,
                    "cursor_missing_timestamp": bool(cursor_stale),
                },
            }
        )

    return {
        "counts": {
            "raw_events": raw_events_total,
            "posted_transactions": posted_total,
            "categorized_transactions": categorized_total,
        },
        "latest_markers": {
            "raw_event_occurred_at": latest_raw_event[0] if latest_raw_event else None,
            "raw_event_source_event_id": latest_raw_event[1] if latest_raw_event else None,
            "connections": connection_summaries,
        },
    }
