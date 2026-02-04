from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import AuditLog, Business


def require_business(db: Session, business_id: str) -> Business:
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(404, "business not found")
    return biz


def log_audit_event(
    db: Session,
    *,
    business_id: str,
    event_type: str,
    actor: str,
    reason: Optional[str] = None,
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
    source_event_id: Optional[str] = None,
    rule_id: Optional[str] = None,
) -> AuditLog:
    row = AuditLog(
        business_id=business_id,
        event_type=event_type,
        actor=actor,
        reason=reason,
        before_state=before,
        after_state=after,
        source_event_id=source_event_id,
        rule_id=rule_id,
    )
    db.add(row)
    return row


def list_audit_events(
    db: Session,
    business_id: str,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    require_business(db, business_id)

    rows = (
        db.execute(
            select(AuditLog)
            .where(AuditLog.business_id == business_id)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )

    return [
        {
            "id": row.id,
            "business_id": row.business_id,
            "event_type": row.event_type,
            "actor": row.actor,
            "reason": row.reason,
            "source_event_id": row.source_event_id,
            "rule_id": row.rule_id,
            "before_state": row.before_state,
            "after_state": row.after_state,
            "created_at": row.created_at,
        }
        for row in rows
    ]
