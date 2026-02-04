from __future__ import annotations

from dataclasses import asdict
from datetime import date
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from backend.app.models import Account, Business, Category, HealthSignalState, RawEvent, TxnCategorization
from backend.app.norma.from_events import raw_event_to_txn
from backend.app.norma.ledger import LedgerIntegrityError, build_cash_ledger
from backend.app.norma.normalize import NormalizedTransaction
from backend.app.services import audit_service, health_signal_service


logger = logging.getLogger(__name__)


DETECTOR_METADATA: Dict[str, Dict[str, Any]] = {
    "expense_creep_by_vendor": {
        "type": "expense_creep_by_vendor",
        "title": "Expense creep by vendor",
        "description": "Identifies vendors with a sustained increase in outflows over a recent window.",
        "recommended_actions": [
            "Review vendor invoices for pricing changes.",
            "Confirm contract terms and check for duplicate charges.",
            "Identify opportunities to renegotiate or consolidate spend.",
        ],
    },
    "low_cash_runway": {
        "type": "low_cash_runway",
        "title": "Low cash runway",
        "description": "Detects when cash runway falls below defined thresholds based on recent burn.",
        "recommended_actions": [
            "Reforecast cash flow and adjust discretionary spend.",
            "Accelerate collections or delay noncritical outflows.",
            "Review burn assumptions and update runway targets.",
        ],
    },
    "unusual_outflow_spike": {
        "type": "unusual_outflow_spike",
        "title": "Unusual outflow spike",
        "description": "Flags outflow spikes that deviate from recent spending patterns.",
        "recommended_actions": [
            "Validate the transaction details for one-off expenses.",
            "Confirm approvals for unusually large payments.",
            "Investigate potential anomalies or fraud.",
        ],
    },
}

EVIDENCE_FIELDS: Dict[str, List[Dict[str, str]]] = {
    "expense_creep_by_vendor": [
        {"key": "vendor_name", "label": "Vendor", "path": "vendor_name", "source": "runtime"},
        {"key": "current_total", "label": "Current total", "path": "current_total", "source": "runtime"},
        {"key": "prior_total", "label": "Prior total", "path": "prior_total", "source": "runtime"},
        {"key": "delta", "label": "Delta", "path": "delta", "source": "derived"},
        {"key": "increase_pct", "label": "Increase (%)", "path": "increase_pct", "source": "derived"},
        {"key": "window_days", "label": "Window (days)", "path": "window_days", "source": "state"},
        {"key": "threshold_pct", "label": "Threshold (%)", "path": "threshold_pct", "source": "state"},
        {"key": "min_delta", "label": "Minimum delta", "path": "min_delta", "source": "state"},
        {"key": "current_window.start", "label": "Current window start", "path": "current_window.start", "source": "runtime"},
        {"key": "current_window.end", "label": "Current window end", "path": "current_window.end", "source": "runtime"},
        {"key": "prior_window.start", "label": "Prior window start", "path": "prior_window.start", "source": "runtime"},
        {"key": "prior_window.end", "label": "Prior window end", "path": "prior_window.end", "source": "runtime"},
    ],
    "low_cash_runway": [
        {"key": "current_cash", "label": "Current cash", "path": "current_cash", "source": "runtime"},
        {"key": "runway_days", "label": "Runway (days)", "path": "runway_days", "source": "derived"},
        {"key": "burn_window_days", "label": "Burn window (days)", "path": "burn_window_days", "source": "state"},
        {"key": "total_inflow", "label": "Total inflow", "path": "total_inflow", "source": "runtime"},
        {"key": "total_outflow", "label": "Total outflow", "path": "total_outflow", "source": "runtime"},
        {"key": "net_burn", "label": "Net burn", "path": "net_burn", "source": "derived"},
        {"key": "burn_per_day", "label": "Burn per day", "path": "burn_per_day", "source": "derived"},
        {"key": "burn_start", "label": "Burn start", "path": "burn_start", "source": "runtime"},
        {"key": "burn_end", "label": "Burn end", "path": "burn_end", "source": "runtime"},
        {"key": "thresholds.high", "label": "High threshold (days)", "path": "thresholds.high", "source": "state"},
        {"key": "thresholds.medium", "label": "Medium threshold (days)", "path": "thresholds.medium", "source": "state"},
    ],
    "unusual_outflow_spike": [
        {"key": "latest_date", "label": "Latest date", "path": "latest_date", "source": "runtime"},
        {"key": "latest_total", "label": "Latest total", "path": "latest_total", "source": "runtime"},
        {"key": "mean_30d", "label": "30d mean", "path": "mean_30d", "source": "derived"},
        {"key": "std_30d", "label": "30d std dev", "path": "std_30d", "source": "derived"},
        {"key": "sigma_threshold", "label": "Sigma threshold", "path": "sigma_threshold", "source": "state"},
        {"key": "trailing_mean_days", "label": "Trailing mean days", "path": "trailing_mean_days", "source": "state"},
        {"key": "trailing_mean", "label": "Trailing mean", "path": "trailing_mean", "source": "derived"},
        {"key": "mult_threshold", "label": "Multiplier threshold", "path": "mult_threshold", "source": "state"},
        {"key": "window_days", "label": "Window (days)", "path": "window_days", "source": "state"},
        {"key": "spike_sigma", "label": "Spike sigma", "path": "spike_sigma", "source": "state"},
        {"key": "spike_mult", "label": "Spike multiplier", "path": "spike_mult", "source": "state"},
    ],
}

AUDIT_EVENT_TYPES = {
    "signal_detected",
    "signal_updated",
    "signal_resolved",
    "signal_status_changed",
}


def _is_dev_env() -> bool:
    return (
        os.getenv("ENV", "").lower() in {"dev", "development", "local"}
        or os.getenv("APP_ENV", "").lower() in {"dev", "development", "local"}
        or os.getenv("NODE_ENV", "").lower() in {"dev", "development"}
    )


def v1_signals_enabled() -> bool:
    return os.getenv("ENABLE_V1_SIGNALS", "").strip().lower() in {"1", "true", "yes", "on"}


def _require_business(db: Session, business_id: str) -> Business:
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="business not found")
    return biz


def _date_range_filter(occurred_at: date, start: date, end: date) -> bool:
    return start <= occurred_at <= end


def _fetch_posted_transactions(
    db: Session,
    business_id: str,
    start_date: date,
    end_date: date,
) -> List[NormalizedTransaction]:
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
        if not _date_range_filter(ev.occurred_at.date(), start_date, end_date):
            continue
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


def fetch_signals(
    db: Session,
    business_id: str,
    start_date: date,
    end_date: date,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not v1_signals_enabled():
        raise HTTPException(status_code=404, detail="v1 signals disabled")
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date range: {start_date} → {end_date}",
        )

    _require_business(db, business_id)

    txns = _fetch_posted_transactions(db, business_id, start_date, end_date)
    if not txns:
        return [], {
            "reason": "not_enough_data",
            "detail": "No posted transactions in the selected date range.",
        }

    try:
        ledger = build_cash_ledger(txns, opening_balance=0.0)
        from backend.app.signals.core import generate_core_signals

        signals = generate_core_signals(txns, ledger)
    except LedgerIntegrityError as exc:
        if _is_dev_env():
            logger.warning(
                "[signals] ledger integrity failed business=%s error=%s",
                business_id,
                str(exc),
            )
        return [], {
            "reason": "integrity_error",
            "detail": str(exc),
        }

    return [asdict(signal) for signal in signals], {"count": len(signals)}


def list_signal_states(db: Session, business_id: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    _require_business(db, business_id)

    rows = (
        db.execute(
            select(HealthSignalState)
            .where(HealthSignalState.business_id == business_id)
            .order_by(HealthSignalState.updated_at.desc())
        )
        .scalars()
        .all()
    )

    signals = [
        {
            "id": row.signal_id,
            "type": row.signal_type,
            "severity": row.severity,
            "status": row.status,
            "title": row.title,
            "summary": row.summary,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in rows
    ]
    return signals, {"count": len(signals)}


def get_signal_state_detail(db: Session, business_id: str, signal_id: str) -> Dict[str, Any]:
    _require_business(db, business_id)
    state = db.get(HealthSignalState, (business_id, signal_id))
    if not state:
        raise HTTPException(status_code=404, detail="signal not found")
    return {
        "id": state.signal_id,
        "type": state.signal_type,
        "severity": state.severity,
        "status": state.status,
        "title": state.title,
        "summary": state.summary,
        "payload_json": state.payload_json,
        "fingerprint": state.fingerprint,
        "detected_at": state.detected_at.isoformat() if state.detected_at else None,
        "last_seen_at": state.last_seen_at.isoformat() if state.last_seen_at else None,
        "resolved_at": state.resolved_at.isoformat() if state.resolved_at else None,
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
    }


def available_signal_types() -> List[Dict[str, Any]]:
    return [
        {
            "type": "cash_runway_trend",
            "window_days": 30,
            "required_inputs": ["transactions", "ledger", "outflow", "cash_balance"],
        },
        {
            "type": "expense_creep",
            "window_days": 30,
            "required_inputs": ["transactions", "outflow", "category"],
        },
        {
            "type": "revenue_volatility",
            "window_days": 60,
            "required_inputs": ["transactions", "weekly_inflows"],
        },
        {
            "type": "expense_creep_by_vendor",
            "window_days": 14,
            "required_inputs": ["transactions", "outflow", "vendor"],
        },
        {
            "type": "low_cash_runway",
            "window_days": 30,
            "required_inputs": ["transactions", "cash_series", "burn_rate"],
        },
        {
            "type": "unusual_outflow_spike",
            "window_days": 30,
            "required_inputs": ["transactions", "daily_outflow"],
        },
    ]


def update_signal_status(
    db: Session,
    business_id: str,
    signal_id: str,
    status: str,
    reason: Optional[str] = None,
    actor: Optional[str] = None,
) -> Dict[str, Any]:
    return health_signal_service.update_signal_status(
        db,
        business_id,
        signal_id,
        status=status,
        reason=reason,
        actor=actor,
    )


def _read_payload_value(payload: Dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        if part not in current:
            return None
        current = current[part]
    return current


def _build_evidence(signal_type: Optional[str], payload: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not signal_type or not isinstance(payload, dict):
        return []
    fields = EVIDENCE_FIELDS.get(signal_type, [])
    evidence: List[Dict[str, Any]] = []
    for field in fields:
        value = _read_payload_value(payload, field["path"])
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            continue
        evidence.append(
            {
                "key": field["key"],
                "label": field["label"],
                "value": value,
                "source": field["source"],
            }
        )
    return sorted(evidence, key=lambda item: item["key"])


def _detector_meta(signal_type: Optional[str], state: HealthSignalState) -> Dict[str, Any]:
    if signal_type and signal_type in DETECTOR_METADATA:
        return DETECTOR_METADATA[signal_type]
    return {
        "type": signal_type or "unknown",
        "title": state.title or "Signal",
        "description": state.summary or "",
        "recommended_actions": [],
    }


def _audit_references_signal(entry: Dict[str, Any], signal_id: str) -> bool:
    for key in ("before_state", "after_state"):
        state = entry.get(key)
        if isinstance(state, dict) and state.get("signal_id") == signal_id:
            return True
    return False


def _list_related_audits(
    db: Session,
    business_id: str,
    signal_id: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    payload = audit_service.list_audit_events(db, business_id, limit=50)
    items = payload.get("items", [])
    related: List[Dict[str, Any]] = []
    for entry in items:
        if entry.get("event_type") not in AUDIT_EVENT_TYPES:
            continue
        if not _audit_references_signal(entry, signal_id):
            continue
        after_state = entry.get("after_state") or {}
        related.append(
            {
                "id": entry.get("id"),
                "event_type": entry.get("event_type"),
                "actor": entry.get("actor"),
                "reason": entry.get("reason"),
                "status": after_state.get("status"),
                "created_at": entry.get("created_at").isoformat()
                if entry.get("created_at")
                else None,
            }
        )
        if len(related) >= limit:
            break
    return related


def get_signal_explain(db: Session, business_id: str, signal_id: str) -> Dict[str, Any]:
    _require_business(db, business_id)
    state = db.get(HealthSignalState, (business_id, signal_id))
    if not state:
        raise HTTPException(status_code=404, detail="signal not found")

    evidence = _build_evidence(state.signal_type, state.payload_json)
    detector = _detector_meta(state.signal_type, state)
    related_audits = _list_related_audits(db, business_id, signal_id)

    return {
        "business_id": business_id,
        "signal_id": signal_id,
        "state": {
            "status": state.status,
            "severity": state.severity,
            "created_at": state.detected_at.isoformat() if state.detected_at else None,
            "updated_at": state.updated_at.isoformat() if state.updated_at else None,
            "last_seen_at": state.last_seen_at.isoformat() if state.last_seen_at else None,
            "resolved_at": state.resolved_at.isoformat() if state.resolved_at else None,
            "metadata": state.payload_json,
        },
        "detector": detector,
        "evidence": evidence,
        "related_audits": related_audits,
        "links": [
            "/signals",
            f"/app/{business_id}/signals",
        ],
    }
