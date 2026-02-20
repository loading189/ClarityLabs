from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.api.deps import require_membership_dep
from backend.app.db import get_db
from backend.app.models import WorkItem
from backend.app.services import work_engine_service

router = APIRouter(prefix="/api/work", tags=["work"])


class SnoozeWorkIn(BaseModel):
    snoozed_until: datetime


@router.get("", dependencies=[Depends(require_membership_dep())])
def get_work_items(
    business_id: str = Query(...),
    status: Optional[str] = Query(default=None),
    priority_gte: Optional[int] = Query(default=None),
    due_before: Optional[datetime] = Query(default=None),
    assigned_only: bool = Query(default=False),
    case_severity_gte: Optional[str] = Query(default=None),
    sort: str = Query(default="priority"),
    db: Session = Depends(get_db),
):
    items = work_engine_service.list_work_items(
        db,
        business_id=business_id,
        status=status,
        priority_gte=priority_gte,
        due_before=due_before,
        assigned_only=assigned_only,
        case_severity_gte=case_severity_gte,
        sort=sort,
    )
    return {"items": items, "total": len(items)}


@router.post("/materialize", dependencies=[Depends(require_membership_dep(min_role="staff"))])
def post_materialize_work(
    case_id: str = Query(...),
    business_id: str = Query(...),
    db: Session = Depends(get_db),
):
    case = work_engine_service.case_engine_service._require_case(db, case_id)
    if case.business_id != business_id:
        raise HTTPException(status_code=404, detail="case not found")
    rows = work_engine_service.materialize_work_items_for_case(db, case_id)
    db.commit()
    return {"items": [{"id": row.id, "idempotency_key": row.idempotency_key, "status": row.status} for row in rows]}


@router.post("/{work_item_id}/complete", dependencies=[Depends(require_membership_dep(min_role="staff"))])
def post_complete_work_item(work_item_id: str, business_id: str = Query(...), db: Session = Depends(get_db)):
    existing = db.get(WorkItem, work_item_id)
    if not existing or existing.business_id != business_id:
        raise HTTPException(status_code=404, detail="work item not found")
    row = work_engine_service.complete_work_item(db, work_item_id)
    db.commit()
    return {"ok": True, "id": row.id, "status": row.status}


@router.post("/{work_item_id}/snooze", dependencies=[Depends(require_membership_dep(min_role="staff"))])
def post_snooze_work_item(work_item_id: str, req: SnoozeWorkIn, business_id: str = Query(...), db: Session = Depends(get_db)):
    existing = db.get(WorkItem, work_item_id)
    if not existing or existing.business_id != business_id:
        raise HTTPException(status_code=404, detail="work item not found")
    row = work_engine_service.snooze_work_item(db, work_item_id, snoozed_until=req.snoozed_until)
    db.commit()
    return {"ok": True, "id": row.id, "status": row.status, "snoozed_until": row.snoozed_until}
