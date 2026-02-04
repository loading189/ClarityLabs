from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.services import signals_service

router = APIRouter(prefix="/api/signals", tags=["signals"])


class SignalsResponse(BaseModel):
    signals: List[Dict[str, Any]]
    meta: Dict[str, Any]


class SignalStatusUpdateIn(BaseModel):
    status: str = Field(..., min_length=2, max_length=32)
    reason: Optional[str] = Field(default=None, max_length=500)
    actor: Optional[str] = Field(default=None, max_length=40)


class SignalStatusUpdateOut(BaseModel):
    business_id: str
    signal_id: str
    status: str
    last_seen_at: Optional[str]
    resolved_at: Optional[str]
    resolution_note: Optional[str]
    reason: Optional[str]
    audit_id: str


@router.get("", response_model=SignalsResponse)
def list_signals(
    business_id: str = Query(...),
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: Session = Depends(get_db),
):
    signals, meta = signals_service.fetch_signals(db, business_id, start_date, end_date)
    return SignalsResponse(signals=signals, meta=meta)


@router.get("/types", response_model=List[Dict[str, Any]])
def list_signal_types(
    include_inputs: Optional[bool] = Query(True),
):
    types = signals_service.available_signal_types()
    if not include_inputs:
        return [{"type": row["type"], "window_days": row["window_days"]} for row in types]
    return types


@router.post("/{business_id}/{signal_id}/status", response_model=SignalStatusUpdateOut)
def update_signal_status(
    business_id: str,
    signal_id: str,
    req: SignalStatusUpdateIn,
    db: Session = Depends(get_db),
):
    return signals_service.update_signal_status(
        db,
        business_id,
        signal_id,
        status=req.status,
        reason=req.reason,
        actor=req.actor,
    )
