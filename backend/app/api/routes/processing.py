from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.services import processing_service


router = APIRouter(prefix="/processing", tags=["processing"])


class ReprocessIn(BaseModel):
    mode: str = "from_last_cursor"
    from_source_event_id: Optional[str] = None


def _dev_ops_allowed() -> bool:
    return os.getenv("DEV_PROCESSING_OPS", "true").lower() == "true"


def _require_dev_ops() -> None:
    if not _dev_ops_allowed():
        raise HTTPException(403, "dev processing ops disabled")


@router.post("/reprocess/{business_id}")
def reprocess_pipeline(
    business_id: str,
    req: ReprocessIn,
    db: Session = Depends(get_db),
):
    if req.mode == "from_beginning":
        _require_dev_ops()
    return processing_service.reprocess_pipeline(
        db,
        business_id=business_id,
        mode=req.mode,
        from_source_event_id=req.from_source_event_id,
    )
