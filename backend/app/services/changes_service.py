from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import AuditLog, Business
from backend.app.services.signals_service import SIGNAL_CATALOG


def _require_business(db: Session, business_id: str) -> None:
    if not db.get(Business, business_id):
        raise HTTPException(status_code=404, detail="business not found")


def _signal_id_from_audit(row: AuditLog) -> Optional[str]:
    for payload in (row.after_state, row.before_state):
        if isinstance(payload, dict):
            signal_id = payload.get("signal_id")
            if signal_id:
                return str(signal_id)
    return None


def _state_from_audit(row: AuditLog) -> Dict[str, Any]:
    if isinstance(row.after_state, dict):
        return row.after_state
    if isinstance(row.before_state, dict):
        return row.before_state
    return {}


def _event_type(row: AuditLog) -> Optional[str]:
    if row.event_type == "signal_detected":
        return "signal_detected"
    if row.event_type == "signal_resolved":
        return "signal_resolved"
    if row.event_type not in {"signal_status_changed", "signal_status_updated"}:
        return None

    before = row.before_state if isinstance(row.before_state, dict) else {}
    after = row.after_state if isinstance(row.after_state, dict) else {}
    before_status = before.get("status")
    after_status = after.get("status")
    if after_status == "resolved" and before_status != "resolved":
        return "signal_resolved"
    return "signal_status_updated"


def _summary(event_type: str, title: str, status: Optional[str]) -> str:
    if event_type == "signal_detected":
        return f"Detected: {title}."
    if event_type == "signal_resolved":
        return f"Resolved: {title}."
    normalized = (status or "updated").replace("_", " ")
    return f"Status updated: {title} ({normalized})."


def list_changes(db: Session, business_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    _require_business(db, business_id)
    rows = (
        db.execute(
            select(AuditLog)
            .where(AuditLog.business_id == business_id)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(max(1, min(limit, 200)) * 3)
        )
        .scalars()
        .all()
    )

    changes: List[Dict[str, Any]] = []
    for row in rows:
        event_type = _event_type(row)
        if not event_type:
            continue
        signal_id = _signal_id_from_audit(row)
        if not signal_id:
            continue

        state = _state_from_audit(row)
        signal_type = state.get("signal_type")
        catalog = SIGNAL_CATALOG.get(signal_type or "", {})
        title = state.get("title") or catalog.get("title")
        severity = state.get("severity")
        domain = catalog.get("domain")
        status = state.get("status")

        changes.append(
            {
                "id": row.id,
                "occurred_at": row.created_at.isoformat() if row.created_at else None,
                "type": event_type,
                "business_id": business_id,
                "signal_id": signal_id,
                "severity": severity,
                "domain": domain,
                "title": title,
                "actor": row.actor,
                "reason": row.reason,
                "summary": _summary(event_type, title or signal_id, status),
                "links": {
                    "assistant": f"/app/{business_id}/assistant?signalId={signal_id}",
                    "signals": f"/app/{business_id}/signals?signalId={signal_id}",
                },
            }
        )
        if len(changes) >= limit:
            break
    return changes


def list_changes_window(db: Session, business_id: str, *, since_hours: int = 72, limit: int = 50) -> List[Dict[str, Any]]:
    _require_business(db, business_id)
    bounded_limit = max(1, min(limit, 200))
    since = datetime.now(timezone.utc) - timedelta(hours=max(1, since_hours))
    rows = (
        db.execute(
            select(AuditLog)
            .where(
                AuditLog.business_id == business_id,
                AuditLog.created_at >= since,
            )
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(bounded_limit * 3)
        )
        .scalars()
        .all()
    )

    changes: List[Dict[str, Any]] = []
    for row in rows:
        event_type = _event_type(row)
        if not event_type:
            continue
        signal_id = _signal_id_from_audit(row)
        if not signal_id:
            continue

        state = _state_from_audit(row)
        signal_type = state.get("signal_type")
        catalog = SIGNAL_CATALOG.get(signal_type or "", {})
        title = state.get("title") or catalog.get("title")
        severity = state.get("severity")
        domain = catalog.get("domain")
        status = state.get("status")

        changes.append(
            {
                "id": row.id,
                "occurred_at": row.created_at.isoformat() if row.created_at else None,
                "type": event_type,
                "business_id": business_id,
                "signal_id": signal_id,
                "severity": severity,
                "domain": domain,
                "title": title,
                "actor": row.actor,
                "reason": row.reason,
                "summary": _summary(event_type, title or signal_id, status),
                "links": {
                    "assistant": f"/app/{business_id}/assistant?signalId={signal_id}",
                    "signals": f"/app/{business_id}/signals?signalId={signal_id}",
                },
            }
        )
        if len(changes) >= bounded_limit:
            break
    return changes
