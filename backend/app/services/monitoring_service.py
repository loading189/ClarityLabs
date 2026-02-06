from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import (
    AuditLog,
    Business,
    HealthSignalState,
    MonitorRuntime,
    RawEvent,
)
from backend.app.norma.normalize import NormalizedTransaction
from backend.app.services import audit_service
from backend.app.services.health_signal_service import ALLOWED_STATUSES
from backend.app.services.posted_txn_service import fetch_posted_transactions
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
    return fetch_posted_transactions(db, business_id)


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


def _fetch_newest_event_cursor(db: Session, business_id: str) -> Tuple[Optional[datetime], Optional[str]]:
    row = (
        db.execute(
            select(RawEvent.occurred_at, RawEvent.source_event_id)
            .where(RawEvent.business_id == business_id)
            .order_by(RawEvent.occurred_at.desc(), RawEvent.source_event_id.desc())
            .limit(1)
        )
        .first()
    )
    if not row:
        return None, None
    occurred_at, source_event_id = row
    return _normalize_dt(occurred_at), source_event_id


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
        payload_changed = before_state.get("payload_json") != signal.payload
        if state.status not in ALLOWED_STATUSES:
            state.status = "open"
        if state.status == "ignored":
            target_status = "ignored"
        elif state.status == "resolved":
            target_status = "open"
        else:
            target_status = state.status
        state.last_seen_at = now
        state.signal_type = signal.signal_type
        state.fingerprint = signal.fingerprint
        state.severity = signal.severity
        state.title = signal.title
        state.summary = signal.summary
        state.payload_json = signal.payload
        if target_status != state.status:
            if state.status == "resolved" and target_status == "open":
                state.resolved_at = None
            state.status = target_status

        if _signal_changed(before_state, signal, target_status):
            state.updated_at = now
            touched.append(signal.signal_id)
            if payload_changed:
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
        if state.status == "ignored":
            continue
        if state.status not in {"open", "in_progress"}:
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

    db.flush()
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
    newest_event_at, newest_event_source_event_id = _fetch_newest_event_cursor(db, business_id)

    runtime = _get_or_create_runtime(db, business_id)
    runtime_last = _normalize_dt(runtime.last_pulse_at)
    runtime_newest = _normalize_dt(runtime.newest_event_at)
    runtime_source_event_id = runtime.newest_event_source_event_id
    if (
        not force_run
        and runtime_last
        and runtime_newest == newest_event_at
        and runtime_source_event_id == newest_event_source_event_id
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
            "newest_event_source_event_id": runtime.newest_event_source_event_id,
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
    runtime.newest_event_source_event_id = newest_event_source_event_id
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
        "newest_event_source_event_id": runtime.newest_event_source_event_id,
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
    now = _now()
    runtime = db.get(MonitorRuntime, business_id)
    newest_event_at, newest_event_source_event_id = _fetch_newest_event_cursor(db, business_id)
    gating_reason = None
    gating_reason_code = None
    gated = False
    stale = False
    stale_reason = None
    runtime_last = _normalize_dt(runtime.last_pulse_at) if runtime else None
    runtime_newest = _normalize_dt(runtime.newest_event_at) if runtime else None
    if runtime_last:
        if (now - runtime_last) > timedelta(hours=6):
            stale = True
            stale_reason = "Last monitoring pulse is older than 6 hours."
    else:
        stale = True
        stale_reason = "Monitoring has not run yet."

    if runtime_last and runtime_newest == newest_event_at and runtime.newest_event_source_event_id == newest_event_source_event_id:
        if (now - runtime_last) < timedelta(minutes=10):
            gated = True
            gating_reason_code = "cooldown"
            gating_reason = "Cooldown: last pulse was under 10 minutes ago and no new events have arrived."
        else:
            gated = True
            gating_reason_code = "no_new_events"
            gating_reason = "No new events since the last pulse. Monitoring will resume when new events arrive."
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
        "newest_event_at": newest_event_at,
        "newest_event_source_event_id": newest_event_source_event_id,
        "open_count": open_count,
        "counts": counts,
        "gated": gated,
        "gating_reason": gating_reason,
        "gating_reason_code": gating_reason_code,
        "stale": stale,
        "stale_reason": stale_reason,
    }
