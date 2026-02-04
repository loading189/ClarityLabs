from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.services import monitoring_service

router = APIRouter(prefix="/monitor", tags=["monitoring"])


@router.get("/status/{business_id}")
def get_monitor_status(business_id: str, db: Session = Depends(get_db)):
    return monitoring_service.get_monitor_status(db, business_id)
