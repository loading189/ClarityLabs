from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from backend.app.models import (
    Account,
    AuditLog,
    Business,
    Category,
    HealthSignalState,
    RawEvent,
    TxnCategorization,
)
from backend.app.norma.categorize_brain import brain
from backend.app.norma.from_events import raw_event_to_txn
from backend.app.norma.merchant import canonical_merchant_name, merchant_key
from backend.app.norma.category_engine import suggest_category
from backend.app.services.category_resolver import resolve_system_key
from backend.app.services.ledger_service import ledger_context_for_source_event
from backend.app.services import signals_service


def _require_business(db: Session, business_id: str) -> Business:
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="business not found")
    return biz


def _payload_value(payload: Dict[str, Any], keys: List[str]) -> Optional[Any]:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return None


def _transaction_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    inner = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
    if not isinstance(inner, dict):
        return {}
    txn = inner.get("transaction")
    if isinstance(txn, dict):
        return txn
    return inner


def _has_explicit_direction(payload: Dict[str, Any]) -> bool:
    txn_payload = _transaction_payload(payload)
    return _payload_value(txn_payload, ["direction", "txn_direction", "transaction_direction"]) is not None


def _counterparty_from_payload(payload: Dict[str, Any]) -> bool:
    txn_payload = _transaction_payload(payload)
    return _payload_value(txn_payload, ["merchant_name", "name", "merchant", "counterparty"]) is not None


def _build_processing_assumptions(
    payload: Dict[str, Any],
    has_categorization: bool,
) -> List[Dict[str, str]]:
    assumptions: List[Dict[str, str]] = []
    if _has_explicit_direction(payload):
        assumptions.append({"field": "direction", "detail": "Direction read from payload."})
    else:
        assumptions.append({"field": "direction", "detail": "Direction derived from amount sign."})

    if _counterparty_from_payload(payload):
        assumptions.append({"field": "counterparty", "detail": "Counterparty sourced from payload."})
    else:
        assumptions.append({"field": "counterparty", "detail": "Counterparty inferred from description."})

    if has_categorization:
        assumptions.append({"field": "category", "detail": "Category assigned via categorization workflow."})
    else:
        assumptions.append({"field": "category", "detail": "Category left uncategorized for review."})

    return assumptions


def _category_suggestion_for_txn(
    db: Session,
    business_id: str,
    txn,
) -> Optional[Dict[str, Any]]:
    suggested = suggest_category(db, txn, business_id=business_id)
    cat_obj = getattr(suggested, "categorization", None)
    if not cat_obj:
        return None
    candidate = (cat_obj.category or "").strip().lower()
    if not candidate or candidate == "uncategorized":
        return None
    resolved = resolve_system_key(db, business_id, candidate)
    if not resolved:
        return None
    return {
        "system_key": candidate,
        "category_id": resolved["category_id"],
        "category_name": resolved["category_name"],
        "source": (cat_obj.source or "rule").strip().lower(),
        "confidence": float(cat_obj.confidence or 0.0),
        "reason": cat_obj.reason or "—",
    }


def _related_signals(
    db: Session,
    business_id: str,
    source_event_id: str,
    vendor: Optional[str],
) -> List[Dict[str, Any]]:
    vendor_norm = (vendor or "").strip().lower()
    rows = (
        db.execute(select(HealthSignalState).where(HealthSignalState.business_id == business_id))
        .scalars()
        .all()
    )
    related: List[Dict[str, Any]] = []
    for row in rows:
        payload = row.payload_json or {}
        if not isinstance(payload, dict):
            payload = {}
        matched_on: Optional[str] = None

        evidence_ids = payload.get("evidence_source_event_ids")
        if isinstance(evidence_ids, list) and source_event_id in {str(item) for item in evidence_ids}:
            matched_on = "evidence_source_event_ids"
        else:
            evidence_txn_ids = payload.get("evidence_txn_ids")
            if isinstance(evidence_txn_ids, list) and source_event_id in {
                str(item) for item in evidence_txn_ids
            }:
                matched_on = "evidence_txn_ids"
            else:
                txn_ids = payload.get("txn_ids")
                if isinstance(txn_ids, list) and source_event_id in {str(item) for item in txn_ids}:
                    matched_on = "txn_ids"
                else:
                    vendor_fields = [
                        payload.get("vendor"),
                        payload.get("vendor_name"),
                        payload.get("counterparty_name"),
                        payload.get("merchant_name"),
                    ]
                    vendor_fields = [str(v).strip().lower() for v in vendor_fields if v]
                    if vendor_norm and any(vendor_norm == v for v in vendor_fields):
                        matched_on = "vendor"

        if not matched_on:
            continue

        facts = payload.get("facts") if isinstance(payload.get("facts"), dict) else None
        if facts is None and isinstance(payload.get("metrics"), dict):
            facts = payload.get("metrics")

        related.append(
            {
                "signal_id": row.signal_id,
                "title": row.title,
                "severity": row.severity,
                "status": row.status,
                "domain": row.signal_type,
                "updated_at": row.updated_at,
                "matched_on": matched_on,
                "window": {
                    "start": payload.get("window_start") or payload.get("date_start"),
                    "end": payload.get("window_end") or payload.get("date_end"),
                },
                "facts": facts,
                "recommended_actions": signals_service._normalize_recommended_actions(
                    row.signal_type or "",
                    signals_service.SIGNAL_CATALOG.get(row.signal_type or "", {}).get(
                        "recommended_actions"
                    ),
                ),
            }
        )

    related.sort(key=lambda item: (item.get("updated_at") or datetime.min), reverse=True)
    return related


def transaction_detail(db: Session, business_id: str, source_event_id: str) -> Dict[str, Any]:
    _require_business(db, business_id)

    raw_event = db.execute(
        select(RawEvent).where(
            and_(
                RawEvent.business_id == business_id,
                RawEvent.source_event_id == source_event_id,
            )
        )
    ).scalar_one_or_none()
    if not raw_event:
        raise HTTPException(status_code=404, detail="transaction not found")

    txn = raw_event_to_txn(raw_event.payload, raw_event.occurred_at, raw_event.source_event_id)
    mk = merchant_key(txn.description or "")

    categorization_row = db.execute(
        select(TxnCategorization, Category, Account)
        .join(Category, Category.id == TxnCategorization.category_id)
        .join(Account, Account.id == Category.account_id)
        .where(
            and_(
                TxnCategorization.business_id == business_id,
                TxnCategorization.source_event_id == source_event_id,
            )
        )
    ).first()

    categorization = None
    if categorization_row:
        txnc, cat, acct = categorization_row
        categorization = {
            "category_id": cat.id,
            "category_name": cat.name,
            "system_key": cat.system_key,
            "account_id": acct.id,
            "account_name": acct.name,
            "source": txnc.source,
            "confidence": txnc.confidence,
            "note": txnc.note,
            "created_at": txnc.created_at,
            "rule_id": None,
        }

    vendor_label = brain.lookup_label(business_id=business_id, alias_key=mk)
    if vendor_label and (vendor_label.system_key or "").strip().lower() != "uncategorized":
        vendor_normalization = {"canonical_name": vendor_label.canonical_name, "source": "vendor_memory"}
    else:
        vendor_normalization = {
            "canonical_name": canonical_merchant_name(txn.description or "Unknown"),
            "source": "inferred",
        }

    audit_rows = (
        db.execute(
            select(AuditLog)
            .where(
                and_(
                    AuditLog.business_id == business_id,
                    AuditLog.source_event_id == source_event_id,
                )
            )
            .order_by(AuditLog.created_at.desc())
        )
        .scalars()
        .all()
    )
    audit_history = [
        {
            "id": row.id,
            "event_type": row.event_type,
            "actor": row.actor,
            "reason": row.reason,
            "before_state": row.before_state,
            "after_state": row.after_state,
            "rule_id": row.rule_id,
            "created_at": row.created_at,
        }
        for row in audit_rows
    ]
    if categorization and audit_rows:
        for row in audit_rows:
            if row.rule_id:
                categorization["rule_id"] = row.rule_id
                break

    processing_assumptions = _build_processing_assumptions(
        raw_event.payload if isinstance(raw_event.payload, dict) else {},
        categorization is not None,
    )

    ledger_context = ledger_context_for_source_event(db, business_id, source_event_id)

    related = _related_signals(db, business_id, source_event_id, vendor_normalization.get("canonical_name"))

    signal_ids = {item["signal_id"] for item in related if item.get("signal_id")}
    if signal_ids:
        signal_audits = (
            db.execute(
                select(AuditLog)
                .where(
                    and_(
                        AuditLog.business_id == business_id,
                        AuditLog.event_type.in_(
                            [
                                "signal_status_changed",
                                "signal_resolved",
                                "signal_updated",
                                "signal_detected",
                            ]
                        ),
                    )
                )
                .order_by(AuditLog.created_at.desc())
            )
            .scalars()
            .all()
        )
        for row in signal_audits:
            after_state = row.after_state if isinstance(row.after_state, dict) else {}
            before_state = row.before_state if isinstance(row.before_state, dict) else {}
            signal_id = after_state.get("signal_id") or before_state.get("signal_id")
            if signal_id and signal_id in signal_ids:
                audit_history.append(
                    {
                        "id": row.id,
                        "event_type": row.event_type,
                        "actor": row.actor,
                        "reason": row.reason,
                        "before_state": row.before_state,
                        "after_state": row.after_state,
                        "rule_id": row.rule_id,
                        "created_at": row.created_at,
                    }
                )

    audit_history.sort(
        key=lambda row: row.get("created_at") or datetime.min,
        reverse=True,
    )

    normalized_txn = {
        "source_event_id": txn.source_event_id,
        "occurred_at": txn.occurred_at,
        "date": txn.date,
        "description": txn.description,
        "amount": txn.amount,
        "direction": txn.direction,
        "account": txn.account,
        "category_hint": txn.category,
        "counterparty_hint": txn.counterparty_hint,
        "merchant_key": mk,
    }

    suggested_category = _category_suggestion_for_txn(db, business_id, txn)
    rule_suggestion = None
    if suggested_category:
        rule_suggestion = {
            "contains_text": vendor_normalization.get("canonical_name") or txn.description,
            "category_id": suggested_category["category_id"],
            "category_name": suggested_category["category_name"],
            "direction": txn.direction,
            "account": txn.account,
        }

    return {
        "business_id": business_id,
        "source_event_id": source_event_id,
        "raw_event": {
            "source": raw_event.source,
            "source_event_id": raw_event.source_event_id,
            "payload": raw_event.payload,
            "occurred_at": raw_event.occurred_at,
            "created_at": raw_event.created_at,
            "processed_at": raw_event.processed_at,
        },
        "normalized_txn": normalized_txn,
        "vendor_normalization": vendor_normalization,
        "categorization": categorization,
        "suggested_category": suggested_category,
        "rule_suggestion": rule_suggestion,
        "processing_assumptions": processing_assumptions,
        "ledger_context": ledger_context,
        "audit_history": audit_history,
        "related_signals": related,
    }
