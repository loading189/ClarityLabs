from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.services.assistant_work_queue_service import WorkQueueOut, list_work_queue

router = APIRouter(prefix="/api/assistant/work_queue", tags=["assistant"])


@router.get("", response_model=WorkQueueOut)
def get_assistant_work_queue(
    business_id: str = Query(...),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return list_work_queue(db, business_id, limit)
