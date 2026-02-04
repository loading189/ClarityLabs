from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
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
    db.flush()
    return row


def _encode_cursor(created_at: datetime, audit_id: str) -> str:
    return f"{created_at.isoformat()}|{audit_id}"


def _decode_cursor(cursor: str) -> Tuple[datetime, str]:
    try:
        created_at_raw, audit_id = cursor.split("|", 1)
        return datetime.fromisoformat(created_at_raw), audit_id
    except ValueError as exc:
        raise HTTPException(400, "invalid cursor") from exc


def list_audit_events(
    db: Session,
    business_id: str,
    limit: int = 100,
    cursor: Optional[str] = None,
    event_type: Optional[str] = None,
    actor: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> Dict[str, Any]:
    require_business(db, business_id)

    query = select(AuditLog).where(AuditLog.business_id == business_id)
    if event_type:
        query = query.where(AuditLog.event_type == event_type)
    if actor:
        query = query.where(AuditLog.actor == actor)
    if since:
        query = query.where(AuditLog.created_at >= since)
    if until:
        query = query.where(AuditLog.created_at <= until)
    if cursor:
        cursor_created_at, cursor_id = _decode_cursor(cursor)
        query = query.where(
            or_(
                AuditLog.created_at < cursor_created_at,
                and_(AuditLog.created_at == cursor_created_at, AuditLog.id < cursor_id),
            )
        )

    rows = (
        db.execute(
            query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit + 1)
        )
        .scalars()
        .all()
    )

    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = _encode_cursor(last.created_at, last.id)
        rows = rows[:limit]

    items = [
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

    return {"items": items, "next_cursor": next_cursor}
