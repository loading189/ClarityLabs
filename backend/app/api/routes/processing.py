from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.services import processing_service

router = APIRouter(prefix="/processing", tags=["processing"])


class ReprocessRequest(BaseModel):
    mode: str = "from_last_cursor"
    from_source_event_id: Optional[str] = None


@router.post("/reprocess/{business_id}")
def reprocess(business_id: str, req: ReprocessRequest, db: Session = Depends(get_db)):
    return processing_service.reprocess_pipeline(
        db,
        business_id=business_id,
        mode=req.mode,
        from_source_event_id=req.from_source_event_id,
    )
