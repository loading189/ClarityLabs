from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from backend.app.models import (
    Account,
    AuditLog,
    Business,
    Category,
    HealthSignalState,
    MonitorRuntime,
    RawEvent,
    TxnCategorization,
)
from backend.app.norma.from_events import raw_event_to_txn
from backend.app.norma.normalize import NormalizedTransaction
from backend.app.services import audit_service
from backend.app.signals.v2 import DetectorRunSummary, DetectedSignal, run_v2_detectors_with_summary


MONITOR_SIGNAL_TYPES = {
    "expense_creep_by_vendor",
    "low_cash_runway",
    "unusual_outflow_spike",
    "liquidity.runway_low",
    "liquidity.cash_trend_down",
    "revenue.decline_vs_baseline",
    "revenue.volatility_spike",
    "expense.spike_vs_baseline",
    "expense.new_recurring",
    "timing.inflow_outflow_mismatch",
    "timing.payroll_rent_cliff",
    "concentration.revenue_top_customer",
    "concentration.expense_top_vendor",
    "hygiene.uncategorized_high",
    "hygiene.signal_flapping",
}

FLAPPING_EVENT_TYPES = {
    "signal_detected",
    "signal_updated",
    "signal_resolved",
    "signal_status_changed",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_dt(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def require_business(db: Session, business_id: str) -> Business:
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="business not found")
    return biz


def _serialize_state(state: HealthSignalState) -> Dict[str, Any]:
    return {
        "signal_id": state.signal_id,
        "signal_type": state.signal_type,
        "fingerprint": state.fingerprint,
        "status": state.status,
        "severity": state.severity,
        "title": state.title,
        "summary": state.summary,
        "payload_json": state.payload_json,
        "detected_at": state.detected_at.isoformat() if state.detected_at else None,
        "last_seen_at": state.last_seen_at.isoformat() if state.last_seen_at else None,
        "resolved_at": state.resolved_at.isoformat() if state.resolved_at else None,
        "resolution_note": state.resolution_note,
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
    }


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


def _fetch_signal_audit_entries(
    db: Session,
    business_id: str,
    since: datetime,
) -> List[Dict[str, object]]:
    rows = (
        db.execute(
            select(AuditLog)
            .where(
                AuditLog.business_id == business_id,
                AuditLog.event_type.in_(FLAPPING_EVENT_TYPES),
                AuditLog.created_at >= since,
            )
            .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": row.id,
            "event_type": row.event_type,
            "created_at": row.created_at,
            "after_state": row.after_state,
        }
        for row in rows
    ]


def _get_or_create_runtime(db: Session, business_id: str) -> MonitorRuntime:
    runtime = db.get(MonitorRuntime, business_id)
    if runtime:
        return runtime
    runtime = MonitorRuntime(business_id=business_id)
    db.add(runtime)
    db.flush()
    return runtime


def _signal_changed(before: Dict[str, Any], signal: DetectedSignal, new_status: str) -> bool:
    return any(
        [
            before.get("severity") != signal.severity,
            before.get("title") != signal.title,
            before.get("summary") != signal.summary,
            before.get("payload_json") != signal.payload,
            before.get("status") != new_status,
        ]
    )


def _upsert_signal_states(
    db: Session,
    business_id: str,
    detected_signals: List[DetectedSignal],
    now: datetime,
) -> List[str]:
    existing_states = (
        db.execute(
            select(HealthSignalState).where(
                HealthSignalState.business_id == business_id,
                HealthSignalState.signal_type.in_(MONITOR_SIGNAL_TYPES),
            )
        )
        .scalars()
        .all()
    )
    existing_by_id = {state.signal_id: state for state in existing_states}
    detected_ids = {signal.signal_id for signal in detected_signals}

    touched: List[str] = []

    for signal in detected_signals:
        state = existing_by_id.get(signal.signal_id)
        if not state:
            state = HealthSignalState(
                business_id=business_id,
                signal_id=signal.signal_id,
                signal_type=signal.signal_type,
                fingerprint=signal.fingerprint,
                status="open",
                severity=signal.severity,
                title=signal.title,
                summary=signal.summary,
                payload_json=signal.payload,
                detected_at=now,
                last_seen_at=now,
                updated_at=now,
            )
            db.add(state)
            touched.append(signal.signal_id)
            audit_service.log_audit_event(
                db,
                business_id=business_id,
                event_type="signal_detected",
                actor="system",
                reason="detected",
                before=None,
                after=_serialize_state(state),
            )
            continue

        before_state = _serialize_state(state)
        new_status = "open" if state.status == "resolved" else state.status
        state.last_seen_at = now
        state.signal_type = signal.signal_type
        state.fingerprint = signal.fingerprint
        state.severity = signal.severity
        state.title = signal.title
        state.summary = signal.summary
        state.payload_json = signal.payload
        if state.status == "resolved":
            state.status = "open"
            state.resolved_at = None

        if _signal_changed(before_state, signal, new_status):
            state.updated_at = now
            touched.append(signal.signal_id)
            audit_service.log_audit_event(
                db,
                business_id=business_id,
                event_type="signal_updated",
                actor="system",
                reason="updated",
                before=before_state,
                after=_serialize_state(state),
            )

    for state in existing_states:
        if state.signal_id in detected_ids:
            continue
        if state.status == "resolved":
            continue
        before_state = _serialize_state(state)
        state.status = "resolved"
        state.resolved_at = now
        state.updated_at = now
        touched.append(state.signal_id)
        audit_service.log_audit_event(
            db,
            business_id=business_id,
            event_type="signal_resolved",
            actor="system",
            reason="auto_resolve",
            before=before_state,
            after=_serialize_state(state),
        )

    return touched


def _count_states(states: List[HealthSignalState]) -> Dict[str, Dict[str, int]]:
    by_status: Dict[str, int] = {}
    by_severity: Dict[str, int] = {}
    for state in states:
        by_status[state.status] = by_status.get(state.status, 0) + 1
        if state.severity:
            by_severity[state.severity] = by_severity.get(state.severity, 0) + 1
    return {"by_status": by_status, "by_severity": by_severity}


def pulse(
    db: Session,
    business_id: str,
    now: Optional[datetime] = None,
    *,
    include_detector_results: bool = False,
    force_run: bool = False,
) -> Dict[str, Any]:
    require_business(db, business_id)
    now = _normalize_dt(now) or _now()

    newest_event_at = db.execute(
        select(func.max(RawEvent.occurred_at)).where(RawEvent.business_id == business_id)
    ).scalar_one_or_none()
    newest_event_at = _normalize_dt(newest_event_at)

    runtime = _get_or_create_runtime(db, business_id)
    runtime_last = _normalize_dt(runtime.last_pulse_at)
    runtime_newest = _normalize_dt(runtime.newest_event_at)
    if (
        not force_run
        and runtime_last
        and runtime_newest == newest_event_at
        and (now - runtime_last) < timedelta(minutes=10)
    ):
        states = (
            db.execute(select(HealthSignalState).where(HealthSignalState.business_id == business_id))
            .scalars()
            .all()
        )
        response = {
            "ran": False,
            "last_pulse_at": runtime.last_pulse_at,
            "newest_event_at": runtime.newest_event_at,
            "counts": _count_states(states),
            "touched_signal_ids": [],
        }
        if include_detector_results:
            response["detector_results"] = []
        return response

    txns = _fetch_posted_transactions(db, business_id)
    audit_entries = _fetch_signal_audit_entries(db, business_id, now - timedelta(days=14))
    detector_summary: DetectorRunSummary = run_v2_detectors_with_summary(
        business_id,
        txns,
        audit_entries=audit_entries,
    )
    touched = _upsert_signal_states(db, business_id, detector_summary.signals, now)

    runtime.last_pulse_at = now
    runtime.newest_event_at = newest_event_at
    runtime.updated_at = now
    db.commit()

    states = (
        db.execute(select(HealthSignalState).where(HealthSignalState.business_id == business_id))
        .scalars()
        .all()
    )
    response = {
        "ran": True,
        "last_pulse_at": runtime.last_pulse_at,
        "newest_event_at": runtime.newest_event_at,
        "counts": _count_states(states),
        "touched_signal_ids": touched,
    }
    if include_detector_results:
        response["detector_results"] = [
            {
                "detector_id": row.detector_id,
                "signal_id": row.signal_id,
                "domain": row.domain,
                "ran": row.ran,
                "skipped_reason": row.skipped_reason,
                "fired": row.fired,
                "severity": row.severity,
                "evidence_keys": row.evidence_keys,
            }
            for row in detector_summary.detectors
        ]
    return response


def get_monitor_status(db: Session, business_id: str) -> Dict[str, Any]:
    require_business(db, business_id)
    runtime = db.get(MonitorRuntime, business_id)
    states = (
        db.execute(
            select(HealthSignalState).where(
                HealthSignalState.business_id == business_id,
                HealthSignalState.signal_type.in_(MONITOR_SIGNAL_TYPES),
            )
        )
        .scalars()
        .all()
    )
    counts = _count_states(states)
    open_count = counts["by_status"].get("open", 0)
    return {
        "business_id": business_id,
        "last_pulse_at": runtime.last_pulse_at if runtime else None,
        "newest_event_at": runtime.newest_event_at if runtime else None,
        "open_count": open_count,
        "counts": counts,
    }
