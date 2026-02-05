from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.services.assistant_progress_service import ProgressOut, get_progress

router = APIRouter(prefix="/api/assistant/progress", tags=["assistant"])


@router.get("", response_model=ProgressOut)
def get_assistant_progress(
    business_id: str = Query(...),
    window_days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
):
    try:
        return get_progress(db, business_id, window_days)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
