from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.services import categorize_service


router = APIRouter(prefix="/api/categorize", tags=["categorize"])


class AutoCategorizeOut(BaseModel):
    status: str
    applied: int
    audit_id: str | None = None


@router.post("/auto/{business_id}", response_model=AutoCategorizeOut)
def auto_categorize(business_id: str, db: Session = Depends(get_db)):
    return AutoCategorizeOut(**categorize_service.auto_categorize_from_vendor_map(db, business_id))
