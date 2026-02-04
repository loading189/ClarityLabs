from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.services import signals_service

router = APIRouter(prefix="/api/signals", tags=["signals"])


class SignalsResponse(BaseModel):
    signals: List[Dict[str, Any]]
    meta: Dict[str, Any]


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
