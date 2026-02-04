from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from backend.app.models import Business, HealthSignalState
from backend.app.services import audit_service

ALLOWED_STATUSES = {"open", "in_progress", "resolved", "ignored"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def require_business(db: Session, business_id: str) -> Business:
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="business not found")
    return biz


def _status_default(signal_status: Optional[str]) -> str:
    if signal_status in ALLOWED_STATUSES:
        return signal_status
    return "open"


def _serialize_state(state: HealthSignalState) -> dict:
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

def _is_missing_health_signal_table(exc: Exception) -> bool:
    orig = getattr(exc, "orig", None)
    if getattr(orig, "__class__", None) and orig.__class__.__name__ == "UndefinedTable":
        return True
    message = str(exc).lower()
    return (
        "undefinedtable" in message
        or "no such table: health_signal_states" in message
        or "relation \"health_signal_states\" does not exist" in message
    )


def _apply_default_states(signals: List[dict]) -> List[dict]:
    for signal in signals:
        signal["status"] = _status_default(signal.get("status"))
        signal.setdefault("last_seen_at", None)
        signal.setdefault("resolved_at", None)
        signal.setdefault("resolution_note", None)
        signal.setdefault("severity", None)
        signal.setdefault("title", None)
        signal.setdefault("summary", None)
        signal.setdefault("payload_json", None)
        signal.setdefault("detected_at", None)
        signal.setdefault("signal_type", None)
        signal.setdefault("fingerprint", None)
        signal.setdefault("updated_at", None)
    return signals




def hydrate_signal_states(
    db: Session,
    business_id: str,
    signals: List[dict],
) -> List[dict]:
    require_business(db, business_id)
    now = _now()
    signal_ids = [s.get("id") for s in signals if s.get("id")]
    if not signal_ids:
        return signals

    try:
        existing = db.execute(
            select(HealthSignalState).where(
                HealthSignalState.business_id == business_id,
                HealthSignalState.signal_id.in_(signal_ids),
            )
        ).scalars().all()
    except (ProgrammingError, OperationalError) as exc:
        if _is_missing_health_signal_table(exc):
            db.rollback()
            return _apply_default_states(signals)
        raise

    existing_map: Dict[str, HealthSignalState] = {row.signal_id: row for row in existing}

    for signal in signals:
        signal_id = signal.get("id")
        if not signal_id:
            continue
        state = existing_map.get(signal_id)
        if not state:
            default_status = _status_default(signal.get("status"))
            state = HealthSignalState(
                business_id=business_id,
                signal_id=signal_id,
                signal_type=signal.get("type") or signal.get("signal_type"),
                status=default_status,
                severity=signal.get("severity"),
                title=signal.get("title"),
                summary=signal.get("summary") or signal.get("short_summary"),
                payload_json=signal.get("payload_json"),
                detected_at=now,
                last_seen_at=now,
                resolved_at=now if default_status == "resolved" else None,
                updated_at=now,
            )
            db.add(state)
            existing_map[signal_id] = state
            audit_service.log_audit_event(
                db,
                business_id=business_id,
                event_type="signal_detected",
                actor="system",
                reason="detected",
                before=None,
                after=_serialize_state(state),
            )
        else:
            state.last_seen_at = now
            state.updated_at = now

        signal["status"] = state.status
        signal["last_seen_at"] = state.last_seen_at.isoformat() if state.last_seen_at else None
        signal["resolved_at"] = state.resolved_at.isoformat() if state.resolved_at else None
        signal["resolution_note"] = state.resolution_note
        signal["severity"] = state.severity
        signal["title"] = state.title
        signal["summary"] = state.summary
        signal["payload_json"] = state.payload_json
        signal["detected_at"] = state.detected_at.isoformat() if state.detected_at else None
        signal["signal_type"] = state.signal_type
        signal["fingerprint"] = state.fingerprint
        signal["updated_at"] = state.updated_at.isoformat() if state.updated_at else None

    db.commit()
    return signals


def update_signal_status(
    db: Session,
    business_id: str,
    signal_id: str,
    status: str,
    reason: Optional[str] = None,
    actor: Optional[str] = None,
    resolution_note: Optional[str] = None,
) -> dict:
    require_business(db, business_id)
    if status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="invalid status")

    now = _now()
    state = db.get(HealthSignalState, (business_id, signal_id))
    before_state = _serialize_state(state) if state else None
    resolved_reason = reason or resolution_note
    resolved_actor = actor or "system"
    if not state:
        state = HealthSignalState(
            business_id=business_id,
            signal_id=signal_id,
            status=status,
            detected_at=now,
            last_seen_at=now,
            resolved_at=now if status == "resolved" else None,
            resolution_note=resolved_reason,
            updated_at=now,
        )
        db.add(state)
        audit_service.log_audit_event(
            db,
            business_id=business_id,
            event_type="signal_detected",
            actor="system",
            reason="detected",
            before=None,
            after=_serialize_state(state),
        )
    else:
        state.status = status
        state.resolution_note = resolved_reason
        state.updated_at = now
        if status == "resolved":
            state.resolved_at = now
        else:
            state.resolved_at = None

    audit_row = audit_service.log_audit_event(
        db,
        business_id=business_id,
        event_type="signal_status_changed",
        actor=resolved_actor,
        reason=resolved_reason,
        before=before_state,
        after=_serialize_state(state),
    )
    db.commit()
    return {
        "business_id": business_id,
        "signal_id": signal_id,
        "status": state.status,
        "last_seen_at": state.last_seen_at.isoformat() if state.last_seen_at else None,
        "resolved_at": state.resolved_at.isoformat() if state.resolved_at else None,
        "resolution_note": state.resolution_note,
        "reason": state.resolution_note,
        "audit_id": audit_row.id,
    }
