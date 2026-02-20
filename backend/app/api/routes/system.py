from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.api.deps import require_membership_dep
from backend.app.db import get_db
from backend.app.services import tick_service

router = APIRouter(prefix="/api/system", tags=["system"])


class TickRequest(BaseModel):
    business_id: str
    apply_recompute: bool = False
    materialize_work: bool = True
    bucket: Optional[str] = None
    limit_cases: Optional[int] = None


@router.post("/tick", dependencies=[Depends(require_membership_dep(min_role="staff"))])
def post_tick(req: TickRequest, db: Session = Depends(get_db)):
    result = tick_service.run_tick(
        db,
        business_id=req.business_id,
        bucket=req.bucket,
        apply_recompute=req.apply_recompute,
        materialize_work=req.materialize_work,
        limit_cases=req.limit_cases,
    )
    db.commit()
    return result


@router.get("/last-tick", dependencies=[Depends(require_membership_dep())])
def get_last_tick(business_id: str = Query(...), db: Session = Depends(get_db)):
    row = tick_service.get_last_tick(db, business_id=business_id)
    if not row:
        return None
    result = row.result_json or {}
    return {
        "business_id": row.business_id,
        "bucket": row.bucket,
        "finished_at": row.finished_at,
        "result_summary": {
            "cases_processed": result.get("cases_processed", 0),
            "cases_recompute_changed": result.get("cases_recompute_changed", 0),
            "cases_recompute_applied": result.get("cases_recompute_applied", 0),
            "work_items_created": result.get("work_items_created", 0),
            "work_items_updated": result.get("work_items_updated", 0),
            "work_items_auto_resolved": result.get("work_items_auto_resolved", 0),
            "work_items_unchanged": result.get("work_items_unchanged", 0),
        },
    }
