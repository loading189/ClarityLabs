from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.models import ActionItem, Business
from backend.app.services.actions_service import (
    generate_actions_for_business,
    list_actions,
    resolve_action,
    snooze_action,
)


router = APIRouter(prefix="/api/actions", tags=["actions"])


def require_business(db: Session, business_id: str) -> Business:
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(404, "business not found")
    return biz


class ActionItemOut(BaseModel):
    id: str
    business_id: str
    action_type: str
    title: str
    summary: str
    priority: int
    status: str
    created_at: datetime
    updated_at: datetime
    due_at: Optional[datetime]
    source_signal_id: Optional[str]
    evidence_json: Optional[dict]
    rationale_json: Optional[dict]
    resolution_reason: Optional[str]
    resolved_at: Optional[datetime]
    snoozed_until: Optional[datetime]
    idempotency_key: str

    class Config:
        from_attributes = True


class ActionListOut(BaseModel):
    actions: list[ActionItemOut]
    summary: dict


class ActionResolveIn(BaseModel):
    status: str
    resolution_reason: Optional[str] = None


class ActionSnoozeIn(BaseModel):
    until: datetime
    reason: Optional[str] = None


@router.get("/{business_id}", response_model=ActionListOut)
def get_actions(
    business_id: str,
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    require_business(db, business_id)
    actions, summary = list_actions(db, business_id, status=status, limit=limit, offset=offset)
    return {"actions": actions, "summary": summary}


@router.post("/{business_id}/refresh", response_model=ActionListOut)
def refresh_actions(business_id: str, db: Session = Depends(get_db)):
    require_business(db, business_id)
    generate_actions_for_business(db, business_id)
    db.commit()
    actions, summary = list_actions(db, business_id, status="open", limit=50, offset=0)
    return {"actions": actions, "summary": summary}


@router.post("/{business_id}/{action_id}/resolve", response_model=ActionItemOut)
def resolve_action_item(
    business_id: str,
    action_id: str,
    req: ActionResolveIn,
    db: Session = Depends(get_db),
):
    require_business(db, business_id)
    try:
        row = resolve_action(
            db,
            business_id,
            action_id,
            status=req.status,
            resolution_reason=req.resolution_reason,
        )
    except ValueError as exc:
        message = str(exc)
        raise HTTPException(404 if "not found" in message else 400, message) from exc
    db.commit()
    db.refresh(row)
    return row


@router.post("/{business_id}/{action_id}/snooze", response_model=ActionItemOut)
def snooze_action_item(
    business_id: str,
    action_id: str,
    req: ActionSnoozeIn,
    db: Session = Depends(get_db),
):
    require_business(db, business_id)
    try:
        row = snooze_action(
            db,
            business_id,
            action_id,
            until=req.until,
            reason=req.reason,
        )
    except ValueError as exc:
        message = str(exc)
        raise HTTPException(404 if "not found" in message else 400, message) from exc
    db.commit()
    db.refresh(row)
    return row
