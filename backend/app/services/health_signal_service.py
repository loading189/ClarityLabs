from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from backend.app.models import Business, HealthSignalState

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
                status=default_status,
                last_seen_at=now,
                resolved_at=now if default_status == "resolved" else None,
                updated_at=now,
            )
            db.add(state)
            existing_map[signal_id] = state
        else:
            state.last_seen_at = now
            state.updated_at = now

        signal["status"] = state.status
        signal["last_seen_at"] = state.last_seen_at.isoformat() if state.last_seen_at else None
        signal["resolved_at"] = state.resolved_at.isoformat() if state.resolved_at else None
        signal["resolution_note"] = state.resolution_note

    db.commit()
    return signals


def update_signal_status(
    db: Session,
    business_id: str,
    signal_id: str,
    status: str,
    resolution_note: Optional[str] = None,
) -> dict:
    require_business(db, business_id)
    if status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="invalid status")

    now = _now()
    state = db.get(HealthSignalState, (business_id, signal_id))
    if not state:
        state = HealthSignalState(
            business_id=business_id,
            signal_id=signal_id,
            status=status,
            last_seen_at=now,
            resolved_at=now if status == "resolved" else None,
            resolution_note=resolution_note,
            updated_at=now,
        )
        db.add(state)
    else:
        state.status = status
        state.resolution_note = resolution_note
        state.updated_at = now
        if status == "resolved":
            state.resolved_at = now
        else:
            state.resolved_at = None

    db.commit()
    return {
        "business_id": business_id,
        "signal_id": signal_id,
        "status": state.status,
        "last_seen_at": state.last_seen_at.isoformat() if state.last_seen_at else None,
        "resolved_at": state.resolved_at.isoformat() if state.resolved_at else None,
        "resolution_note": state.resolution_note,
    }
