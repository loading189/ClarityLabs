from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.api.deps import require_membership_dep
from backend.app.db import get_db
from backend.app.services import audit_service

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditLogOut(BaseModel):
    id: str
    business_id: str
    event_type: str
    actor: str
    reason: Optional[str] = None
    source_event_id: Optional[str] = None
    rule_id: Optional[str] = None
    before_state: Optional[Dict[str, Any]] = None
    after_state: Optional[Dict[str, Any]] = None
    created_at: datetime


class AuditLogPageOut(BaseModel):
    items: List[AuditLogOut]
    next_cursor: Optional[str] = None


@router.get("/{business_id}", response_model=AuditLogPageOut, dependencies=[Depends(require_membership_dep())])
def list_audit_events(
    business_id: str,
    limit: int = Query(100, ge=1, le=500),
    cursor: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    actor: Optional[str] = Query(None),
    since: Optional[datetime] = Query(None),
    until: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
):
    result = audit_service.list_audit_events(
        db,
        business_id,
        limit=limit,
        cursor=cursor,
        event_type=event_type,
        actor=actor,
        since=since,
        until=until,
    )
    return AuditLogPageOut(
        items=[AuditLogOut(**item) for item in result["items"]],
        next_cursor=result["next_cursor"],
    )
