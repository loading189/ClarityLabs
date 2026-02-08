from __future__ import annotations

from typing import List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.api.deps import require_membership_dep
from backend.app.db import get_db
from backend.app.services import changes_service

router = APIRouter(prefix="/api/changes", tags=["changes"])


class ChangeLinksOut(BaseModel):
    assistant: str
    signals: str


class ChangeEventOut(BaseModel):
    id: str
    occurred_at: Optional[str]
    type: Literal["signal_detected", "signal_resolved", "signal_status_updated"]
    business_id: str
    signal_id: str
    severity: Optional[
        Literal["info", "warning", "critical", "low", "medium", "high", "green", "yellow", "red"]
    ] = None
    domain: Optional[
        Literal[
            "liquidity",
            "revenue",
            "expense",
            "timing",
            "concentration",
            "hygiene",
            "unknown",
        ]
    ] = None
    title: Optional[str] = None
    actor: Optional[str] = None
    reason: Optional[str] = None
    summary: str
    links: ChangeLinksOut


@router.get("", response_model=List[ChangeEventOut], dependencies=[Depends(require_membership_dep())])
def list_changes(
    business_id: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    try:
        UUID(business_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="business_id must be a valid UUID") from exc
    return changes_service.list_changes(db, business_id=business_id, limit=limit)
